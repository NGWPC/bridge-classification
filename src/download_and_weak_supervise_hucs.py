"""
HUC-based Bridge Processing Pipeline

A comprehensive pipeline for processing bridge lidar data organized by Hydrologic
Unit Code (HUC) regions. This script finds intersecting lidar sources, applies
ground filtering and weak supervision rules to generate labeled training data for
machine learning models.

Input Requirements
------------------
Directory Structure:
    hucs_dir/
        {huc_id}/
            osm_bridges_lidar_subset__{huc_id}.gpkg

Usage Examples
-------------
Basic Usage:
    # Process all bridges in all HUCs with default settings
    python src/download_and_weak_supervise_hucs.py

Filtering by HUC:
    # Process bridges in specific HUC regions
    python src/download_and_weak_supervise_hucs.py --hucs 01010001 01010002

Filtering by OSM ID:
    # Process specific bridges by their OpenStreetMap IDs
    python src/download_and_weak_supervise_hucs.py --osm-ids 123456 789012

Custom Configuration:
    # Use custom buffer size and worker count
    python src/download_and_weak_supervise_hucs.py --buffer 15.0 --workers 8

Resume Processing:
    # Skip already processed files and bridges that previously had no lidar points (useful for resuming interrupted runs)
    python src/download_and_weak_supervise_hucs.py --skip-existing

Custom Directories:
    # Specify custom input/output directories
    python src/download_and_weak_supervise_hucs.py \
        --hucs-dir ./data/osm/hucs \
        --source-dir ./data/ml-data/source \
        --silver-dir ./data/ml-data/silver_training \
        --lidar-resources ./data/usgs_entwine/lidar_resources.geojson \
        --log-dir ./logs

Combined Options:
    # Process specific HUCs with custom settings
    python src/download_and_weak_supervise_hucs.py \
        --hucs 01010001 01010002 \
        --buffer 12.0 \
        --workers 16 \
        --skip-existing \
        --no-progress
"""

import geopandas as gpd
import pdal
import json
import os
import sys
import numpy as np
import argparse
import random
import multiprocessing
import logging
import traceback
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.logging_utils import setup_logging
from src.lidar_utils import (
    load_lidar_index as _load_lidar_index,
    find_intersecting_sources as _find_sources,
    safe_source_name as _safe_name,
)
from src.gpkg_utils import read_bridge_gpkg, filter_by_ids, iter_huc_gpkgs, DEFAULT_GPKG_TEMPLATE
from src.weak_supervision import BridgeProcessingConfig, process_bridge

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("Warning: tqdm not available. Progress bars disabled.")


# Type aliases for commonly used complex types
TaskTuple = Tuple[str, str, str, str, str, float, str, str, Dict[str, Any]]  # Task tuple for multiprocessing


# Global logger (will be initialized in main)
logger = None


class LidarSourceFinder:
    """
    Class for finding intersecting lidar sources.
    Loads lidar_resources.geojson and builds spatial index for fast queries.
    """

    def __init__(self, lidar_resources_path: str) -> None:
        """Initialize the finder by loading lidar resources and building spatial index."""
        print(f"[Worker {os.getpid()}] Loading lidar resources from {lidar_resources_path}...")
        self.lidar_gdf = _load_lidar_index(str(lidar_resources_path))
        self.sindex = self.lidar_gdf.sindex if not self.lidar_gdf.empty else None
        print(f"[Worker {os.getpid()}] Loaded {len(self.lidar_gdf)} lidar sources")

    def find_intersecting_sources(self, bridge_geometry: Any, buffer_meters: float = 10) -> List[Dict[str, str]]:
        """Find all lidar sources that intersect with the buffered bridge geometry."""
        return _find_sources(self.lidar_gdf, bridge_geometry, buffer_meters)


class DataManager:
    """Manages file I/O and directory organization."""

    def __init__(self, source_dir: str, silver_dir: str) -> None:
        self.source_dir = Path(source_dir)
        self.silver_dir = Path(silver_dir)

    def get_paths(self, huc_id: str, osmid: str, source_name: str) -> Tuple[str, str]:
        """
        Get file paths for source and silver training outputs.

        Returns:
            Tuple of (source_path, silver_path) as strings for pdal compatibility
        """
        safe_name = _safe_name(source_name)
        source_filename = f"bridge_{osmid}_{safe_name}.laz"
        silver_filename = f"bridge_{osmid}_{safe_name}.laz"

        source_path = self.source_dir / huc_id / source_filename
        silver_path = self.silver_dir / huc_id / silver_filename

        return str(source_path), str(silver_path)

    def ensure_directories(self, huc_id: str) -> None:
        """Create output directories for a HUC if they don't exist."""
        source_huc_dir = self.source_dir / huc_id
        silver_huc_dir = self.silver_dir / huc_id

        source_huc_dir.mkdir(parents=True, exist_ok=True)
        silver_huc_dir.mkdir(parents=True, exist_ok=True)

    def file_exists(self, huc_id: str, osmid: str, source_name: str) -> bool:
        """Check if both source and silver files already exist."""
        source_path, silver_path = self.get_paths(huc_id, osmid, source_name)
        return Path(source_path).exists()

    def no_points_sentinel_path(self, huc_id: str, osmid: str, source_name: str) -> Path:
        """Path to sentinel file indicating no lidar points were found for this bridge/source."""
        safe_name = _safe_name(source_name)
        filename = f"bridge_{osmid}_{safe_name}.no_points"
        return self.source_dir / huc_id / filename

    def no_points_sentinel_exists(self, huc_id: str, osmid: str, source_name: str) -> bool:
        """Check if a no-points sentinel exists (skip on restart with --skip-existing)."""
        return self.no_points_sentinel_path(huc_id, osmid, source_name).exists()

    def write_no_points_sentinel(self, huc_id: str, osmid: str, source_name: str) -> None:
        """Write sentinel so this (huc_id, osmid, source_name) is skipped on restart with --skip-existing."""
        self.ensure_directories(huc_id)
        path = self.no_points_sentinel_path(huc_id, osmid, source_name)
        path.write_text("# No points found in lidar data for this bridge geometry\n")

    def save_files(self, original_arrays: Any, modified_arrays: Any, huc_id: str, osmid: str, source_name: str, config: BridgeProcessingConfig) -> bool:
        """
        Save both source and silver training files.

        Args:
            original_arrays: Arrays after SMRF, before weak supervision classification
            modified_arrays: Arrays after weak supervision classification
            config: BridgeProcessingConfig instance

        Returns:
            True if successful, False otherwise
        """
        try:
            self.ensure_directories(huc_id)
            source_path, silver_path = self.get_paths(huc_id, osmid, source_name)

            # Save source (original with SMRF, before classification)
            writer_source_json = {
                "pipeline": [{
                    "type": "writers.las",
                    "filename": source_path,
                    "a_srs": config.pdal_writer_srs,
                    "extra_dims": "all"
                }]
            }
            pdal.Pipeline(json.dumps(writer_source_json), arrays=[original_arrays]).execute()

            # Save silver (labeled after weak supervision classification)
            writer_silver_json = {
                "pipeline": [{
                    "type": "writers.las",
                    "filename": silver_path,
                    "a_srs": config.pdal_writer_srs,
                    "extra_dims": "all"
                }]
            }
            pdal.Pipeline(json.dumps(writer_silver_json), arrays=[modified_arrays]).execute()

            return True
        except Exception as e:
            print(f"Error saving files for {osmid}/{source_name}: {e}")
            return False

    def save_source_only(self, original_arrays: Any, huc_id: str, osmid: str, source_name: str, config: BridgeProcessingConfig) -> bool:
        """
        Save only the source training file (e.g. when silver is rejected).

        Args:
            original_arrays: Point arrays to write (e.g. raw or SMRF output)
            huc_id: HUC identifier
            osmid: OSM bridge ID
            source_name: Source name for filename
            config: BridgeProcessingConfig instance

        Returns:
            True if successful, False otherwise
        """
        try:
            self.ensure_directories(huc_id)
            source_path, _ = self.get_paths(huc_id, osmid, source_name)
            writer_source_json = {
                "pipeline": [{
                    "type": "writers.las",
                    "filename": source_path,
                    "a_srs": config.pdal_writer_srs,
                    "extra_dims": "all"
                }]
            }
            pdal.Pipeline(json.dumps(writer_source_json), arrays=[original_arrays]).execute()
            return True
        except Exception as e:
            print(f"Error saving source for {osmid}/{source_name}: {e}")
            return False


def process_bridge_source(args: TaskTuple) -> Dict[str, Any]:
    """
    Process a single (bridge, source) pair.
    This function is called by worker processes.

    Args:
        args: Tuple of (huc_id, osmid, bridge_geometry_wkt, source_url, source_name,
                       buffer_meters, source_dir, silver_dir, config_dict)

    Returns:
        Dictionary with keys: 'success' (bool), 'huc_id' (str), 'osmid' (str),
        'source_name' (str), 'error' (Optional[str]), 'rmse' (Optional[float]),
        'deviation' (Optional[float]), 'skipped' (Optional[bool])
    """
    (huc_id, osmid, bridge_geometry_wkt, source_url, source_name,
     buffer_meters, source_dir, silver_dir, config_dict) = args

    try:
        # Reconstruct config from dict
        config = BridgeProcessingConfig.from_dict(config_dict)

        # Reconstruct geometry from WKT
        from shapely import wkt
        bridge_geometry = wkt.loads(bridge_geometry_wkt)

        # Initialize data manager
        data_manager = DataManager(source_dir, silver_dir)

        # Check if already processed
        if data_manager.file_exists(huc_id, osmid, source_name):
            return {
                'success': True,
                'huc_id': huc_id,
                'osmid': osmid,
                'source_name': source_name,
                'skipped': True,
                'error': None
            }

        # Entry log so we know which task is running when the pipeline appears stuck
        print(f"[Task start] huc_id={huc_id} osmid={osmid} source_name={source_name} at {datetime.now().isoformat()}", flush=True)
        if logger:
            logger.info(f"[Task start] huc_id={huc_id} osmid={osmid} source_name={source_name}")

        # Process with weak supervision
        result = process_bridge(source_url, bridge_geometry, config, buffer_meters)

        if result is None or not result.get('success', False):
            error_msg = result.get('error', 'Unknown processing error') if result else 'Processing returned None'
            if result is not None and 'original_arrays' in result:
                data_manager.save_source_only(
                    result['original_arrays'], huc_id, osmid, source_name, config
                )
            else:
                # No file saved (e.g. count==0 from EPT read). Write sentinel so --skip-existing skips on restart.
                if result is not None and error_msg == 'No points found in lidar data for this bridge geometry':
                    data_manager.write_no_points_sentinel(huc_id, osmid, source_name)
            return {
                'success': False,
                'huc_id': huc_id,
                'osmid': osmid,
                'source_name': source_name,
                'error': error_msg
            }

        # Extract both arrays
        original_arrays = result['original_arrays']
        modified_arrays = result['arrays']

        # Save files
        success = data_manager.save_files(
            original_arrays, modified_arrays, huc_id, osmid, source_name, config
        )

        if success:
            return {
                'success': True,
                'huc_id': huc_id,
                'osmid': osmid,
                'source_name': source_name,
                'rmse': result['rmse'],
                'deviation': result['deviation'],
                'error': None
            }
        else:
            error_msg = f'File save failed for {huc_id}/{osmid}/{source_name}'
            return {
                'success': False,
                'huc_id': huc_id,
                'osmid': osmid,
                'source_name': source_name,
                'error': error_msg
            }

    except Exception as e:
        error_msg = f'Exception in process_bridge_source: {str(e)}'
        return {
            'success': False,
            'huc_id': huc_id,
            'osmid': osmid,
            'source_name': source_name,
            'error': error_msg
        }


def _generate_tasks_for_one_huc(args: Tuple[Any, ...]) -> Tuple[List[TaskTuple], Optional[str]]:
    """
    Generate task tuples for a single HUC. Module-level for multiprocessing pickling.

    Args:
        args: Tuple of (huc_id, gpkg_path, osm_ids, lidar_resources_path,
                       buffer_meters, source_dir, silver_dir, config_dict)

    Returns:
        Tuple of (list of task tuples for process_bridge_source, error message or None)
    """
    (huc_id, gpkg_path, osm_ids, lidar_resources_path, buffer_meters,
     source_dir, silver_dir, config_dict) = args

    try:
        config = BridgeProcessingConfig.from_dict(config_dict)
        try:
            gdf = read_bridge_gpkg(gpkg_path, required_cols=("osmid",), target_epsg=config.epsg_code)
        except ValueError:
            return ([], None)

        if osm_ids is not None:
            gdf = filter_by_ids(gdf, "osmid", osm_ids)

        if gdf.empty:
            return ([], None)

        finder = LidarSourceFinder(lidar_resources_path)
        tasks = []

        for idx, row in gdf.iterrows():
            osmid = row['osmid']
            geom = row.geometry
            sources = finder.find_intersecting_sources(geom, buffer_meters)
            if not sources:
                continue
            geom_wkt = geom.wkt
            for source in sources:
                task = (
                    huc_id, osmid, geom_wkt, source['url'], source['name'],
                    buffer_meters, source_dir, silver_dir, config_dict
                )
                tasks.append(task)

        return (tasks, None)
    except OSError as e:
        return ([], f"[{huc_id}] Task generation failed ({gpkg_path}): I/O error: {e}")
    except (ValueError, KeyError) as e:
        return ([], f"[{huc_id}] Task generation failed ({gpkg_path}): config/data error: {type(e).__name__}: {e}")
    except Exception as e:
        return ([], f"[{huc_id}] Task generation failed ({gpkg_path}): {type(e).__name__}: {e}\n{traceback.format_exc()}")


class BridgeProcessor:
    """Main orchestrator class for processing bridges across HUCs."""

    def __init__(self, hucs_dir: str, lidar_resources_path: str, source_dir: str,
                 silver_dir: str, config: BridgeProcessingConfig, buffer_meters: Optional[float] = None,
                 num_workers: Optional[int] = None, skip_existing: bool = False) -> None:
        self.hucs_dir = Path(hucs_dir)
        self.lidar_resources_path = Path(lidar_resources_path)
        self.source_dir = Path(source_dir)
        self.silver_dir = Path(silver_dir)
        self.config = config
        self.buffer_meters = buffer_meters if buffer_meters is not None else config.default_buffer_meters
        self.num_workers = num_workers or multiprocessing.cpu_count()
        self.skip_existing = skip_existing

        # Create base directories
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.silver_dir.mkdir(parents=True, exist_ok=True)

    def find_huc_files(self, huc_ids: Optional[List[str]] = None) -> List[Tuple[str, str]]:
        """
        Find all HUC GPKG files.

        Returns:
            List of (huc_id, file_path) tuples where file_path is a string
        """
        huc_files = []

        if not self.hucs_dir.exists():
            print(f"Error: HUCs directory not found: {self.hucs_dir}")
            return huc_files

        for huc_id, gpkg_path in iter_huc_gpkgs(self.hucs_dir, DEFAULT_GPKG_TEMPLATE, huc_ids):
            huc_files.append((huc_id, str(gpkg_path)))

        return huc_files

    def load_bridges(self, gpkg_path: str, osm_ids: Optional[List[str]] = None) -> gpd.GeoDataFrame:
        """Load bridges from GPKG file, optionally filtered by OSM IDs."""
        try:
            gdf = read_bridge_gpkg(gpkg_path, required_cols=("osmid",), target_epsg=self.config.epsg_code)
        except ValueError:
            print(f"Warning: 'osmid' column not found in {gpkg_path}")
            return gpd.GeoDataFrame()

        if osm_ids is not None:
            gdf = filter_by_ids(gdf, "osmid", osm_ids)

        return gdf

    def generate_tasks(self, huc_ids: Optional[List[str]] = None,
                      osm_ids: Optional[List[str]] = None) -> List[TaskTuple]:
        """
        Generate all (bridge, source) tasks for processing in parallel per HUC.

        Returns:
            List of task tuples for process_bridge_source function
        """
        huc_files = self.find_huc_files(huc_ids)

        if logger:
            logger.info(f"Found {len(huc_files)} HUC file(s) to process")

        if not huc_files:
            return []

        args_list = [
            (
                huc_id, gpkg_path, osm_ids, str(self.lidar_resources_path),
                self.buffer_meters, str(self.source_dir), str(self.silver_dir),
                self.config.to_dict()
            )
            for huc_id, gpkg_path in huc_files
        ]

        pool_size = min(self.num_workers, len(huc_files))
        with multiprocessing.Pool(processes=pool_size) as pool:
            result_lists = pool.map(_generate_tasks_for_one_huc, args_list)

        tasks = []
        for task_list, error_msg in result_lists:
            tasks.extend(task_list)
            if error_msg is not None and logger:
                logger.error(error_msg)

        if logger:
            logger.info(f"Generated {len(tasks)} total tasks for processing (from {len(huc_files)} HUCs)")
        return tasks

    def process(self, huc_ids: Optional[List[str]] = None,
                osm_ids: Optional[List[str]] = None, show_progress: bool = True,
                shuffle_seed: Optional[int] = None) -> None:
        """Main processing method with parallel execution."""
        if logger:
            logger.info("=" * 60)
            logger.info("Starting bridge processing pipeline")
            logger.info(f"HUC IDs: {huc_ids if huc_ids else 'All'}")
            logger.info(f"OSM IDs: {osm_ids if osm_ids else 'All'}")
            logger.info(f"Workers: {self.num_workers}")
            logger.info(f"Buffer: {self.buffer_meters}m")
            logger.info("=" * 60)

        print("Generating tasks...")
        tasks = self.generate_tasks(huc_ids, osm_ids)

        if not tasks:
            msg = "No tasks to process."
            if logger:
                logger.warning(msg)
            print(msg)
            return

        msg = f"Generated {len(tasks)} tasks. Starting parallel processing with {self.num_workers} workers..."
        if logger:
            logger.info(msg)
        print(msg)

        # Filter out existing tasks if skip_existing is True
        if self.skip_existing:
            data_manager = DataManager(self.source_dir, self.silver_dir)
            filtered_tasks = []
            skipped_count = 0

            for task in tasks:
                huc_id, osmid, _, _, source_name, _, _, _, _ = task
                if data_manager.file_exists(huc_id, osmid, source_name) or data_manager.no_points_sentinel_exists(huc_id, osmid, source_name):
                    skipped_count += 1
                else:
                    filtered_tasks.append(task)

            tasks = filtered_tasks
            msg = f"Skipped {skipped_count} already processed or known-empty tasks. {len(tasks)} tasks remaining."
            if logger:
                logger.info(msg)
            print(msg)

        # Shuffle task order so a single stuck bridge does not block the same position every run
        if shuffle_seed is not None:
            random.seed(shuffle_seed)
        random.shuffle(tasks)
        if shuffle_seed is not None:
            if logger:
                logger.info(f"Tasks shuffled (seed={shuffle_seed})")
            print(f"Tasks shuffled (seed={shuffle_seed})")
        else:
            if logger:
                logger.info("Tasks shuffled (random order)")
            print("Tasks shuffled (random order)")

        if not tasks:
            msg = "All tasks already processed."
            if logger:
                logger.info(msg)
            print(msg)
            return

        # Log header before processing so results are written as each task completes
        if logger:
            logger.info("=" * 60)
            logger.info("Processing Results")
            logger.info("=" * 60)

        # Process tasks in parallel; log each result as soon as it completes
        results = []
        with multiprocessing.Pool(processes=self.num_workers, maxtasksperchild=50) as pool:
            # iterator = pool.imap(process_bridge_source, tasks)
            iterator = pool.imap_unordered(process_bridge_source, tasks)
            if show_progress and HAS_TQDM:
                iterator = tqdm(iterator, total=len(tasks), desc="Processing bridges")
            for result in iterator:
                if logger:
                    if result.get('skipped', False):
                        logger.info(f"[{result['huc_id']}] Skipped OSM ID {result['osmid']} / Source {result['source_name']} (already processed)")
                    elif result['success']:
                        rmse = result.get('rmse', 0.0)
                        deviation = result.get('deviation', 0.0)
                        logger.info(f"[{result['huc_id']}] Successfully processed OSM ID {result['osmid']} / Source {result['source_name']} (RMSE: {rmse:.3f}m, Deviation: {deviation:.3f}m)")
                    else:
                        logger.error(f"[{result['huc_id']}] OSM ID {result['osmid']} / Source {result['source_name']}: {result['error']}")
                results.append(result)

        if logger:
            logger.info("=" * 60)

        # Aggregate results
        success_count = sum(1 for r in results if r['success'])
        failed_count = len(results) - success_count
        skipped_count = sum(1 for r in results if r.get('skipped', False))

        # Log and print summary
        summary_msg = f"\n=== Processing Complete ===\n"
        summary_msg += f"Total tasks: {len(results)}\n"
        summary_msg += f"Successful: {success_count}\n"
        summary_msg += f"Failed: {failed_count}\n"
        summary_msg += f"Skipped (already existed): {skipped_count}"

        if logger:
            logger.info("=" * 60)
            logger.info("Processing Summary")
            logger.info(f"Total tasks: {len(results)}")
            logger.info(f"Successful: {success_count}")
            logger.info(f"Failed: {failed_count}")
            logger.info(f"Skipped (already existed): {skipped_count}")
            logger.info("=" * 60)

        print(summary_msg)

        # Print errors if any
        errors = [r for r in results if not r['success'] and not r.get('skipped', False)]
        if errors:
            error_summary = f"\nErrors encountered:"
            if logger:
                logger.error("=" * 60)
                logger.error("Error Summary")
                for err in errors:
                    logger.error(f"[{err['huc_id']}] OSM ID {err['osmid']} / Source {err['source_name']}: {err['error']}")
                logger.error("=" * 60)

            print(error_summary)
            for err in errors[:10]:  # Show first 10 errors
                print(f"  {err['huc_id']}/{err['osmid']}/{err['source_name']}: {err['error']}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors (see log file for complete list)")


def main() -> None:
    """Main entry point with command-line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Process bridges from HUC subfolders with weak supervision'
    )

    parser.add_argument(
        '--hucs',
        nargs='+',
        help='List of HUC IDs to process (default: all)'
    )

    parser.add_argument(
        '--osm-ids',
        nargs='+',
        help='List of OSM IDs to process (default: all)'
    )

    parser.add_argument(
        '--buffer',
        type=float,
        default=10.0,
        help='Buffer size in meters (default: 10)'
    )

    parser.add_argument(
        '--source-dir',
        default='./data/ml-data/source',
        help='Source output directory (default: ./data/ml-data/source)'
    )

    parser.add_argument(
        '--silver-dir',
        default='./data/ml-data/silver_training',
        help='Silver training output directory (default: ./data/ml-data/silver_training)'
    )

    parser.add_argument(
        '--hucs-dir',
        default='./data/osm/hucs',
        help='HUCs input directory (default: ./data/osm/hucs)'
    )

    parser.add_argument(
        '--lidar-resources',
        default='./data/usgs_entwine/lidar_resources.geojson',
        help='Path to lidar_resources.geojson (default: ./data/usgs_entwine/lidar_resources.geojson)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help=f'Number of parallel workers (default: CPU count = {multiprocessing.cpu_count()})'
    )

    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip already processed files (resume capability)'
    )

    parser.add_argument(
        '--shuffle-seed',
        type=int,
        default=None,
        help='Optional seed for task shuffle (reproducible order for debugging). If not set, tasks are shuffled randomly.'
    )

    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bar'
    )

    parser.add_argument(
        '--log-dir',
        default='./logs',
        help='Directory for log files (default: ./logs)'
    )

    args = parser.parse_args()

    global logger
    logger = setup_logging('bridge_processing', args.log_dir)

    # Create configuration instance
    config = BridgeProcessingConfig()
    # Create processor
    processor = BridgeProcessor(
        hucs_dir=args.hucs_dir,
        lidar_resources_path=args.lidar_resources,
        source_dir=args.source_dir,
        silver_dir=args.silver_dir,
        config=config,
        buffer_meters=args.buffer,
        num_workers=args.workers,
        skip_existing=args.skip_existing
    )

    # Process
    processor.process(
        huc_ids=args.hucs,
        osm_ids=args.osm_ids,
        show_progress=not args.no_progress,
        shuffle_seed=args.shuffle_seed
    )


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True)
    main()
