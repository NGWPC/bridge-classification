"""
Bridge Weak Supervision Demo Script

Standalone demo script that processes a small set of target bridges from a
single lidar dataset. Uses the shared weak_supervision module for the core
algorithm (RANSAC plane fitting, linearity checks, Z-distance classification).

This script is a simplified, single-dataset version of the full HUC-based
pipeline (download_and_weak_supervise_hucs.py). It is useful for quickly
testing the weak supervision algorithm on a handful of known bridges.

Usage:
    python src/download_and_weak_supervise_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.gpkg_utils import read_bridge_gpkg, filter_by_ids
from src.las_io import write_las
from src.weak_supervision import BridgeProcessingConfig, process_bridge

# --- CONFIGURATION ---
LIDAR_DATASET = 'GA_Statewide_B4_2018'
# LIDAR_DATASET = 'USGS_LPC_PA_South_Central_B2_2017_LAS_2019'

EPT_URL = f"https://s3-us-west-2.amazonaws.com/usgs-lidar-public/{LIDAR_DATASET}/ept.json"
GPKG_PATH = f'./data/osm/osm_bridges_subset_lidar__{LIDAR_DATASET}.gpkg'

OUTPUT_DIR = f"./data/silver_label_bridges__{LIDAR_DATASET.lower()}"
OUTPUT_DIR_ORIGINAL = f"./data/downloaded_bridges__{LIDAR_DATASET.lower()}"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR_ORIGINAL, exist_ok=True)

# Target OSM IDs to process
# USGS_LPC_PA_South_Central_B2_2017_LAS_2019
# TARGET_OSMIDS = [
#     1174852485, 160697314, 160697359, 1174889151, 1084727916,
#     938406797, 15902209, 506845138, 432595664, 501253066, 706009962,
#     792385722, 5069009, 64914035, 274538735, 492364942
# ]

# GA_Statewide_B4_2018
TARGET_OSMIDS = [
    980194216, 28994716, 39810511, 39811603
]

BUFFER_METERS = 10


def run_weak_supervision_pipeline() -> None:
    print(f"Loading geometry from {GPKG_PATH}...")

    try:
        gdf = read_bridge_gpkg(GPKG_PATH, required_cols=("osmid",), target_epsg=3857)
        bridges = filter_by_ids(gdf, "osmid", TARGET_OSMIDS)

        if bridges.empty:
            print("No matching OSM IDs found.")
            return
        print(f"Found {len(bridges)} bridges. Starting processing loop...")

    except Exception as e:
        print(f"Error reading GPKG: {e}")
        return

    config = BridgeProcessingConfig()
    succeeded = 0
    failed = 0

    for _, row in bridges.iterrows():
        osmid = row['osmid']
        print(f"\n--- Processing OSM ID: {osmid} ---")

        result = process_bridge(EPT_URL, row.geometry, config, BUFFER_METERS)

        if not result or not result.get('success', False):
            error = result.get('error', 'unknown') if result else 'processing returned None'
            print(f" -> Skipped {osmid}: {error}")
            if result and 'original_arrays' in result:
                original_path = os.path.join(OUTPUT_DIR_ORIGINAL, f"original_bridge_{osmid}.laz")
                write_las(original_path, result['original_arrays'])
                print(f" -> Saved original (rejected): {original_path}")
            failed += 1
            continue

        print(f" -> Accepted {osmid}: RMSE={result['rmse']:.3f}m, Deviation={result['deviation']:.3f}m")

        original_path = os.path.join(OUTPUT_DIR_ORIGINAL, f"original_bridge_{osmid}.laz")
        labeled_path = os.path.join(OUTPUT_DIR, f"labeled_bridge_{osmid}.laz")

        write_las(original_path, result['original_arrays'])
        write_las(labeled_path, result['arrays'])
        print(f" -> Saved: {labeled_path}")
        succeeded += 1

    print(f"\nDone: {succeeded} succeeded, {failed} failed out of {len(bridges)}")


if __name__ == "__main__":
    if not TARGET_OSMIDS:
        print("Please add IDs to the TARGET_OSMIDS list.")
    else:
        run_weak_supervision_pipeline()
