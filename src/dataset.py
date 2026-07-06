"""Bridge point cloud dataset with on-the-fly voxelization.

Provides BridgeDataset (PyTorch Dataset) and sparse_collate_fn for
batching voxelized point clouds into sparse tensor format.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import Dataset

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.voxelization import voxelize


class BridgeDataset(Dataset):
    """
    Dataset for bridge point cloud classification with voxelization.

    Handles HUC-organized directory structure and properly aggregates
    points within voxels using majority vote for labels and averaging for features.
    """

    def __init__(
        self,
        data_dir: str,
        voxel_size: float = 0.1,
        augment: bool = False,
        augment_extra: bool = False,
        max_voxels: Optional[int] = None,
    ):
        """
        Args:
            data_dir: Path to directory containing .npy files (can be HUC-organized).
            voxel_size: Voxel size in meters (e.g., 0.1 for 10cm).
            augment: Whether to apply random Z-rotation and jitter.
            augment_extra: Extra augmentation (XY-flip, scaling, intensity jitter, point dropout). Requires augment=True.
            max_voxels: Maximum voxels per sample; randomly subsample if exceeded (default: None = no limit).
        """
        self.data_dir = Path(data_dir)
        self.voxel_size = voxel_size
        self.augment = augment
        self.augment_extra = augment_extra
        self.max_voxels = max_voxels

        # Recursively find all .npy files (handles HUC folder structure)
        self.files = sorted(list(self.data_dir.rglob("*.npy")))

        if not self.files:
            raise ValueError(f"No .npy files found in {data_dir}")

        # Define the ignore label (Background/Unclassified)
        self.ignore_label = 0

        print(f"Found {len(self.files)} bridge files in {data_dir}")

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Load and voxelize a single bridge sample.

        Returns:
            Tuple of (discrete_coords, features, labels)
            - discrete_coords: (N_voxels, 3) integer voxel coordinates
            - features: (N_voxels, 1) averaged intensity per voxel
            - labels: (N_voxels,) majority-vote labels per voxel
        """
        file_path = self.files[idx]

        # 1. Load Data
        data = np.load(file_path)  # Shape: (N, 5) -> [x, y, z, intensity, label]

        xyz = data[:, 0:3]
        feat = data[:, 3:4] # Intensity is the only feature for now
        labels = data[:, 4].astype(np.int64)

        # Preprocessing centers data at the mean (e.g., -50 to +50).
        # SpConv indices MUST be positive (0 to 100)?
        # We shift the min value to 0.0 for every sample.
        xyz -= xyz.min(axis=0)

        # 2. Data Augmentation (Optional)
        if self.augment:
            # Random rotation around Z-axis
            theta = np.random.uniform(0, 2 * np.pi)
            rotation_matrix = np.array([
                [np.cos(theta), -np.sin(theta), 0],
                [np.sin(theta),  np.cos(theta), 0],
                [0,              0,             1]
            ])
            xyz = xyz @ rotation_matrix

            # Random jitter
            jitter = np.random.normal(0, 0.01, size=xyz.shape)
            xyz += jitter

            # Re-shift to positive after rotation (rotation can make things negative again)
            xyz -= xyz.min(axis=0)

            if self.augment_extra:
                # Random XY-flip
                if np.random.random() > 0.5:
                    xyz[:, 0] = -xyz[:, 0]
                if np.random.random() > 0.5:
                    xyz[:, 1] = -xyz[:, 1]

                scale = np.random.uniform(0.9, 1.1)
                xyz *= scale

                # Intensity jitter
                feat = feat + np.random.normal(0, 0.02, size=feat.shape).astype(np.float32)
                feat = np.clip(feat, 0.0, 1.0)

                # Random point dropout (5-10%)
                dropout_rate = np.random.uniform(0.05, 0.10)
                keep_mask = np.random.random(len(xyz)) > dropout_rate
                if keep_mask.sum() > 10:
                    xyz = xyz[keep_mask]
                    feat = feat[keep_mask]
                    labels = labels[keep_mask]

                # Re-shift to positive after flips/scaling
                xyz -= xyz.min(axis=0)

        # 3. Voxelization + feature/label aggregation
        result = voxelize(xyz, self.voxel_size, feat, labels)
        coords = result.unique_coords
        features = result.voxel_features
        agg_labels = result.voxel_labels

        # 4. Subsample if voxel count exceeds max_voxels (prevents OOM on outlier bridges)
        if self.max_voxels is not None and len(coords) > self.max_voxels:
            indices = np.random.choice(len(coords), self.max_voxels, replace=False)
            indices.sort()
            coords = coords[indices]
            features = features[indices]
            agg_labels = agg_labels[indices]

        return coords, features, agg_labels


def sparse_collate_fn(batch: List[Tuple[np.ndarray, np.ndarray, np.ndarray]]) -> Dict[str, torch.Tensor]:
    """
    Custom collate function to create a batch for sparse tensor format.

    Sparse tensors require coordinate format: [Batch_ID, X, Y, Z]

    Args:
        batch: List of (coords, features, labels) tuples

    Returns:
        Dictionary with keys:
        - coordinates: (N_total, 4) tensor [batch_id, x, y, z]
        - features: (N_total, 1) tensor
        - labels: (N_total,) tensor
        - sample_voxel_counts: list of int
    """
    batch_coords = []
    batch_feats = []
    batch_labels = []
    sample_voxel_counts = []

    for batch_id, (coords, feats, labels) in enumerate(batch):
        sample_voxel_counts.append(coords.shape[0])
        # Append the Batch ID as the first column of the coordinates
        # Shape becomes (N, 4): [Batch_ID, X, Y, Z]
        b_idx = np.full((coords.shape[0], 1), batch_id, dtype=np.int32)
        batched_c = np.hstack([b_idx, coords])

        batch_coords.append(batched_c)
        batch_feats.append(feats)
        batch_labels.append(labels)

    # Concatenate all lists into single big tensors
    coords_tensor = torch.from_numpy(np.vstack(batch_coords)).int()
    feats_tensor = torch.from_numpy(np.vstack(batch_feats)).float()
    labels_tensor = torch.from_numpy(np.hstack(batch_labels)).long()

    return {
        "coordinates": coords_tensor,
        "features": feats_tensor,
        "labels": labels_tensor,
        "sample_voxel_counts": sample_voxel_counts,
    }
