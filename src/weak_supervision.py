"""Weak supervision algorithm for bridge LiDAR classification.

Core algorithm for determining linear vs. complex bridges using
RANSAC plane fitting, linearity checking, convex hull masking,
and Z-distance heuristic labeling.
"""

import json
from enum import Enum

import numpy as np
import pdal
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

from sklearn.linear_model import RANSACRegressor, LinearRegression
from sklearn.decomposition import PCA
from scipy.spatial import ConvexHull
from matplotlib.path import Path as MatplotlibPath


class FailureReason(Enum):
    """Why a bridge failed weak supervision.

    Most values are set by process_bridge() itself. TIMEOUT is set by the
    caller's subprocess wrapper — included here so the consumer can dispatch
    on all failure reasons with a single enum.
    """
    NO_POINTS = "no_points"
    RANSAC_INSUFFICIENT = "ransac_insufficient"
    RANSAC_FAILED = "ransac_failed"
    RANSAC_LOW_INLIERS = "ransac_low_inliers"
    HULL_FAILED = "hull_failed"
    HIGH_RMSE = "high_rmse"
    CURVED = "curved"
    EXCEPTION = "exception"
    TIMEOUT = "timeout"


@dataclass
class BridgeProcessingConfig:
    """
    Centralized configuration for bridge processing pipeline.
    Contains all magic numbers, thresholds, and parameters.
    """

    # PDAL Configuration
    # EPT Reader parameters
    pdal_ept_requests: int = 3
    pdal_ept_resolution: float = 0.1

    # SMRF Filter parameters
    pdal_smrf_scalar: float = 1.25
    pdal_smrf_slope: float = 0.05
    pdal_smrf_threshold: float = 0.5
    pdal_smrf_window: float = 10.0
    pdal_smrf_ignore: str = "Classification[7:7]"

    # Writer parameters
    pdal_writer_srs: str = "EPSG:3857"

    # Deterministic Ordering Configuration
    deterministic_ordering_seed: int = 27

    # RANSAC Configuration
    ransac_min_samples: int = 10
    ransac_residual_threshold: float = 0.20
    ransac_random_state: int = 27

    # Linearity Check Configuration
    linearity_num_bins: int = 10
    linearity_deviation_threshold: float = 0.8  # Initial check threshold
    linearity_min_z_points: int = 50
    linearity_min_bridge_length: float = 5.0  # meters
    linearity_min_points_per_bin: int = 5
    linearity_min_skeleton_points: int = 3
    linearity_final_deviation_threshold: float = 0.35  # Final check threshold

    # Processing Thresholds
    min_points_for_ransac: int = 20
    min_ransac_inliers: int = 20
    structure_check_min_z: float = -2.0
    structure_check_max_z: float = 2.0
    max_rmse: float = 0.30

    # Classification Rules
    ignore_classes: Optional[List[int]] = None  # Will default to [7, 9, 18]
    bridge_deck_class: int = 17
    high_noise_class: int = 18
    deck_z_max: float = 0.20
    deck_z_min: float = -0.70
    noise_z_min: float = 0.20
    noise_z_max: float = 15.0

    # PCA Configuration
    pca_n_components: int = 2
    pca_random_state: int = 27

    # Spatial Configuration
    default_buffer_meters: float = 10.0
    epsg_code: int = 3857

    # Timeout Configuration
    bridge_timeout: float = 300.0

    def __post_init__(self):
        """Set default values for mutable types."""
        if self.ignore_classes is None:
            self.ignore_classes = [7, 9, 18]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'BridgeProcessingConfig':
        """Create config from dictionary (for multiprocessing serialization)."""
        # Create a copy to avoid mutating the original
        d = d.copy()
        if 'ignore_classes' in d and isinstance(d['ignore_classes'], list):
            d['ignore_classes'] = list(d['ignore_classes'])
        return cls(**d)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary (for multiprocessing serialization)."""
        return asdict(self)


def check_bridge_linearity(
    xy_points: np.ndarray,
    z_points: np.ndarray,
    config: BridgeProcessingConfig,
    deviation_threshold: Optional[float] = None,
) -> Tuple[bool, float]:
    """
    Slices the bridge into bins, finds the median Z for each bin (the 'skeleton'),
    and checks if that skeleton deviates from a straight line.

    Args:
        xy_points: XY coordinates of points
        z_points: Z coordinates of points
        config: BridgeProcessingConfig instance
        deviation_threshold: Optional threshold override (defaults to config.linearity_deviation_threshold)

    Returns:
        Tuple of (is_curved: bool, max_deviation: float)
    """
    if deviation_threshold is None:
        deviation_threshold = config.linearity_deviation_threshold

    if len(z_points) < config.linearity_min_z_points:
        return False, 0.0

    # 1. Rotate bridge to align with X-axis using PCA
    pca = PCA(n_components=config.pca_n_components, random_state=config.pca_random_state)
    xy_rotated = pca.fit_transform(xy_points)
    x_axis = xy_rotated[:, 0]

    min_x, max_x = np.min(x_axis), np.max(x_axis)

    # If bridge is too short, assume it's flat/keep it
    if (max_x - min_x) < config.linearity_min_bridge_length:
        return False, 0.0

    # 2. Slice and skeletonize
    bin_edges = np.linspace(min_x, max_x, config.linearity_num_bins + 1)
    skeleton_x = []
    skeleton_z = []

    for i in range(config.linearity_num_bins):
        mask = (x_axis >= bin_edges[i]) & (x_axis < bin_edges[i+1])
        if np.sum(mask) < config.linearity_min_points_per_bin:
            # skip empty/low-density bins
            continue

        z_slice = z_points[mask]
        skeleton_z.append(np.median(z_slice))
        bin_center = (bin_edges[i] + bin_edges[i+1]) / 2.0
        skeleton_x.append(bin_center)

    if len(skeleton_x) < config.linearity_min_skeleton_points:
        return False, 0.0

    # 3. Linear Fit to the Skeleton
    X_skel = np.array(skeleton_x).reshape(-1, 1)
    z_skel = np.array(skeleton_z)

    model = LinearRegression()
    model.fit(X_skel, z_skel)
    z_predicted = model.predict(X_skel)

    # 4. Measure Deviation
    deviations = np.abs(z_skel - z_predicted)
    max_deviation = np.max(deviations)

    is_curved = max_deviation > deviation_threshold
    return is_curved, max_deviation


def fit_ransac_from_arrays(
    arrays: np.ndarray,
    config: BridgeProcessingConfig,
) -> Dict[str, Any]:
    """
    Run RANSAC plane fitting on in-memory point arrays (e.g. from LAZ).
    Used for visualization; does not run linearity or RMSE rejection.

    Args:
        arrays: Structured array with fields X, Y, Z, Classification (PDAL-style).
        config: BridgeProcessingConfig instance.

    Returns:
        On success: dict with success=True, x_center, y_center, X_local, Y_local, Z,
            coef_x, coef_y, intercept, inlier_mask_full, lateral_mask, dist_from_plane_all.
        On failure: dict with success=False, error=str.
    """
    # Deterministic ordering (same as process_bridge)
    sort_idx = np.lexsort((arrays['Z'], arrays['Y'], arrays['X']))
    arrays = arrays[sort_idx]
    rng = np.random.default_rng(seed=config.deterministic_ordering_seed)
    shuffle_idx = rng.permutation(len(arrays))
    arrays = arrays[shuffle_idx]

    X = np.asarray(arrays['X'], dtype=np.float64)
    Y = np.asarray(arrays['Y'], dtype=np.float64)
    Z = np.asarray(arrays['Z'], dtype=np.float64)
    Classes = np.asarray(arrays['Classification'], dtype=np.int32)

    x_center = np.mean(X)
    y_center = np.mean(Y)
    X_local = X - x_center
    Y_local = Y - y_center

    fit_mask = ~np.isin(Classes, config.ignore_classes)
    if np.sum(fit_mask) < config.min_points_for_ransac:
        return {
            'success': False,
            'error': f'Not enough points for RANSAC ({np.sum(fit_mask)} < {config.min_points_for_ransac})',
        }

    X_fit = X_local[fit_mask]
    Y_fit = Y_local[fit_mask]
    Z_fit = Z[fit_mask]
    xy_fit = np.stack([X_fit, Y_fit], axis=1)

    if len(np.unique(xy_fit, axis=0)) < config.ransac_min_samples:
        return {'success': False, 'error': 'Not enough unique points for RANSAC'}

    try:
        ransac = RANSACRegressor(
            min_samples=config.ransac_min_samples,
            residual_threshold=config.ransac_residual_threshold,
            random_state=config.ransac_random_state,
        )
        ransac.fit(xy_fit, Z_fit)
        inlier_mask = ransac.inlier_mask_
    except Exception as e:
        return {'success': False, 'error': f'RANSAC fitting failed: {e}'}

    if np.sum(inlier_mask) < config.min_ransac_inliers:
        return {
            'success': False,
            'error': f'Not enough RANSAC inliers ({np.sum(inlier_mask)} < {config.min_ransac_inliers})',
        }

    x_inliers = X_fit[inlier_mask]
    y_inliers = Y_fit[inlier_mask]
    xy_inliers = np.stack([x_inliers, y_inliers], axis=1)

    try:
        hull = ConvexHull(xy_inliers)
        hull_vertices = xy_inliers[hull.vertices]
        hull_path = MatplotlibPath(hull_vertices)
    except Exception as e:
        return {'success': False, 'error': f'Convex hull failed: {e}'}

    xy_local_all = np.stack([X_local, Y_local], axis=1)
    lateral_mask = hull_path.contains_points(xy_local_all)
    predicted_z_all = ransac.predict(xy_local_all)
    dist_from_plane_all = Z - predicted_z_all

    inlier_mask_full = np.zeros(len(X), dtype=bool)
    inlier_mask_full[fit_mask] = inlier_mask

    coef_x, coef_y = ransac.estimator_.coef_
    intercept = ransac.estimator_.intercept_

    return {
        'success': True,
        'x_center': x_center,
        'y_center': y_center,
        'X_local': X_local,
        'Y_local': Y_local,
        'Z': Z,
        'coef_x': coef_x,
        'coef_y': coef_y,
        'intercept': intercept,
        'inlier_mask_full': inlier_mask_full,
        'lateral_mask': lateral_mask,
        'dist_from_plane_all': dist_from_plane_all,
    }


def process_bridge(
    ept_url: str,
    bridge_geometry: Any,
    config: BridgeProcessingConfig,
    buffer_meters: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Process a single bridge with weak supervision rules.

    Args:
        ept_url: EPT URL for the lidar source
        bridge_geometry: Shapely geometry of the bridge
        config: BridgeProcessingConfig instance with all parameters
        buffer_meters: Buffer size in meters (defaults to config.default_buffer_meters)

    Returns:
        Dictionary with keys: 'success' (bool), 'arrays' (numpy structured array),
        'original_arrays' (numpy structured array), 'rmse' (float), 'deviation' (float),
        'error' (str). Returns None if processing failed.
    """
    if buffer_meters is None:
        buffer_meters = config.default_buffer_meters

    buffered_geom = bridge_geometry.buffer(buffer_meters)
    pdal_polygon = buffered_geom.wkt

    # Set after first pipeline run; used for save-on-reject
    original_arrays = None

    # Stage 1: Read only (Get Raw Data)
    read_pipeline_json = {
        "pipeline": [
            {
                "type": "readers.ept",
                "filename": ept_url,
                "polygon": pdal_polygon,
                "requests": config.pdal_ept_requests,
                "resolution": config.pdal_ept_resolution
            }
        ]
    }

    try:
        print("Phase: EPT read 1 start", flush=True)
        pipeline = pdal.Pipeline(json.dumps(read_pipeline_json))
        count = pipeline.execute()

        print("Phase: EPT read 1 done", flush=True)
        if count == 0:
            return {
                'success': False,
                'reason': FailureReason.NO_POINTS,
                'error': 'No points found in lidar data for this bridge geometry'
            }

        original_arrays = pipeline.arrays[0]

        # Stage 2: Process with SMRF
        # Construct PDAL Pipeline (Read + SMRF)
        smrf_pipeline_json = {
            "pipeline": [
                {
                    "type": "readers.ept",
                    "filename": ept_url,
                    "polygon": pdal_polygon,
                    "requests": config.pdal_ept_requests,
                    "resolution": config.pdal_ept_resolution
                },
                {
                    "type": "filters.smrf",
                    "ignore": config.pdal_smrf_ignore,
                    "scalar": config.pdal_smrf_scalar,
                    "slope": config.pdal_smrf_slope,
                    "threshold": config.pdal_smrf_threshold,
                    "window": config.pdal_smrf_window
                }
            ]
        }

        print("Phase: EPT+SMRF start", flush=True)
        smrf_pipeline = pdal.Pipeline(json.dumps(smrf_pipeline_json))
        count = smrf_pipeline.execute()

        print("Phase: EPT+SMRF done", flush=True)
        if count == 0:
            return {
                'success': False,
                'reason': FailureReason.NO_POINTS,
                'error': 'No points found in lidar data for this bridge geometry',
                'original_arrays': original_arrays
            }

        arrays = smrf_pipeline.arrays[0]

        # --- ENFORCE DETERMINISTIC ORDERING ---
        # Sort arrays by X, then Y, then Z to ensure RANSAC sees the
        # exact same indices regardless of OS or download chunking.
        # Using structured array sorting or lexsort.

        # Create a sorting index based on X, Y, Z
        # np.lexsort sorts by the last key passed first, so we pass (Z, Y, X) to sort by X, then Y, then Z
        sort_idx = np.lexsort((arrays['Z'], arrays['Y'], arrays['X']))

        # Reorder the structured array using the sorting index
        arrays = arrays[sort_idx]

        # Shuffle the arrays with a fixed random seed to ensure deterministic ordering of spatial
        # clusters for RANSAC by step 1
        rng = np.random.default_rng(seed=config.deterministic_ordering_seed)
        shuffle_idx = rng.permutation(len(arrays))
        arrays = arrays[shuffle_idx]

        X = arrays['X']
        Y = arrays['Y']
        Z = arrays['Z']
        Classes = arrays['Classification']

        # --- CENTER COORDINATES FOR NUMERICAL STABILITY ---
        # RANSAC fails on Ubuntu because X/Y are huge (e.g. 10,000,000).
        # We shift them to 0,0 temporarily for the math to work safely.
        x_center = np.mean(X)
        y_center = np.mean(Y)

        X_local = X - x_center
        Y_local = Y - y_center

        # --- RANSAC LOGIC ---
        fit_mask = ~np.isin(Classes, config.ignore_classes)

        if np.sum(fit_mask) < config.min_points_for_ransac:
            return {
                'success': False,
                'reason': FailureReason.RANSAC_INSUFFICIENT,
                'error': f'Not enough points for RANSAC fitting ({np.sum(fit_mask)} < {config.min_points_for_ransac})',
                'original_arrays': original_arrays
            }

        # Use local coordinates for fitting
        X_fit = X_local[fit_mask]
        Y_fit = Y_local[fit_mask]
        Z_fit = Z[fit_mask]
        xy_fit = np.stack([X_fit, Y_fit], axis=1)

        if len(np.unique(xy_fit, axis=0)) < config.ransac_min_samples:
            return {
                'success': False,
                'reason': FailureReason.RANSAC_INSUFFICIENT,
                'error': f'Not enough UNIQUE points for RANSAC',
                'original_arrays': original_arrays
            }

        # Fit RANSAC
        print("Phase: RANSAC start", flush=True)
        try:
            ransac = RANSACRegressor(
                min_samples=config.ransac_min_samples,
                residual_threshold=config.ransac_residual_threshold,
                random_state=config.ransac_random_state
            )
            ransac.fit(xy_fit, Z_fit)
            inlier_mask = ransac.inlier_mask_
        except Exception as e:
            return {
                'success': False,
                'reason': FailureReason.RANSAC_FAILED,
                'error': f'RANSAC fitting failed: {str(e)}',
                'original_arrays': original_arrays
            }

        if np.sum(inlier_mask) < config.min_ransac_inliers:
            return {
                'success': False,
                'reason': FailureReason.RANSAC_LOW_INLIERS,
                'error': f'Not enough RANSAC inliers ({np.sum(inlier_mask)} < {config.min_ransac_inliers})',
                'original_arrays': original_arrays
            }

        print("Phase: RANSAC done", flush=True)
        # --- MASKING (CONVEX HULL) ---
        x_inliers = X_fit[inlier_mask]
        y_inliers = Y_fit[inlier_mask]
        xy_inliers = np.stack([x_inliers, y_inliers], axis=1)

        try:
            hull = ConvexHull(xy_inliers)
            hull_vertices = xy_inliers[hull.vertices]
            hull_path = MatplotlibPath(hull_vertices)
        except Exception as e:
            return {
                'success': False,
                'reason': FailureReason.HULL_FAILED,
                'error': f'Convex hull generation failed: {str(e)}',
                'original_arrays': original_arrays
            }

        # Create a global lateral mask for all points based on the convex hull of inliers
        # use local coordinates for the check since the hull is in local coordinates
        xy_local_all = np.stack([X_local, Y_local], axis=1)
        lateral_mask = hull_path.contains_points(xy_local_all)

        # Identify points inside the hull that are NOT deep noise
        predicted_z_all = ransac.predict(xy_local_all)
        dist_from_plane_all = Z - predicted_z_all

        # Points roughly near the bridge plane (for curvature check)
        structure_check_mask = lateral_mask & (dist_from_plane_all > config.structure_check_min_z) & (dist_from_plane_all < config.structure_check_max_z)

        # Use local coordinates for curvature check too (numerically safer)
        xy_check = xy_local_all[structure_check_mask]
        z_check = Z[structure_check_mask]

        # --- CURVATURE CHECKS ---
        # Metric 1: Inlier RMSE
        z_pred_inliers = ransac.predict(xy_inliers)
        z_inliers_fit = Z_fit[inlier_mask]
        rmse_inliers = np.sqrt(np.mean((z_inliers_fit - z_pred_inliers)**2))

        if rmse_inliers > config.max_rmse:
            return {
                'success': False,
                'reason': FailureReason.HIGH_RMSE,
                'error': f'Inlier RMSE too high ({rmse_inliers:.3f}m > {config.max_rmse}m)',
                'original_arrays': original_arrays
            }

        # Metric 2: Linearity (Global Arch/Sag Check)
        print("Phase: linearity check start", flush=True)
        is_curved, deviation = check_bridge_linearity(
            xy_check, z_check, config, deviation_threshold=config.linearity_final_deviation_threshold
        )
        if is_curved:
            return {
                'success': False,
                'reason': FailureReason.CURVED,
                'error': f'Bridge is curved/arched (max deviation: {deviation:.3f}m)',
                'original_arrays': original_arrays
            }

        # --- CLASSIFICATION (HEURISTICS) ---
        new_classes = Classes.copy()

        # Rule A: Bridge Deck (Class 17) = Points within the hull that are close to the plane (Z distance)
        deck_z_mask = (dist_from_plane_all <= config.deck_z_max) & (dist_from_plane_all >= config.deck_z_min)
        final_deck_mask = deck_z_mask & lateral_mask
        # Overwrite SMRF errors (Ground->Bridge) inside the Hull
        new_classes[final_deck_mask] = config.bridge_deck_class

        # Rule B: High Noise / Obstacles (Class 18) = Points within the hull that are far above the plane (Z distance)
        noise_z_mask = (dist_from_plane_all > config.noise_z_min) & (dist_from_plane_all < config.noise_z_max)
        # Only classify noise if it's inside the bridge hull
        final_noise_mask = noise_z_mask & lateral_mask
        new_classes[final_noise_mask] = config.high_noise_class

        # Update Arrays with new classifications
        arrays['Classification'] = new_classes

        print("Phase: done (success)", flush=True)
        return {
            'original_arrays': original_arrays, # Original data before SMRF (for save-on-reject)
            'arrays': arrays, # Final data with SMRF and classifications
            'success': True,
            'rmse': rmse_inliers,
            'deviation': deviation
        }

    except Exception as e:
        out = {'success': False, 'reason': FailureReason.EXCEPTION,
               'error': f'Exception during processing: {str(e)}'}
        if original_arrays is not None:
            out['original_arrays'] = original_arrays
        return out
