"""Prepare a pipeline run from a flat bridge GeoPackage.

Reads a flat GPKG (e.g. from NOAA), splits it into per-HUC directories
matching the structure expected by download_and_weak_supervise_hucs.py,
and scaffolds a self-contained run directory with metadata.

Usage:
    python utils/prepare_run.py \
        --input data/noaa-provided/bridges_without_lidar_tif.gpkg \
        --run-name noaa-bridges-without-tif \
        --huc-column huc8 \
        --osmid-column osmid

Output structure:
    data/runs/{run-name}/
        input/{original_filename}.gpkg
        hucs/{huc_id}/osm_bridges_lidar_subset__{huc_id}.gpkg
        source/
        silver_training/
        predictions/
        run_config.json
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.gpkg_utils import (
    DEFAULT_GPKG_TEMPLATE,
    read_bridge_gpkg,
    split_gpkg_by_column,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a pipeline run from a flat bridge GeoPackage"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to the input GPKG file (flat, all bridges in one file)"
    )
    parser.add_argument(
        "--run-name", required=True,
        help="Short name for this run (used as directory name under runs-dir)"
    )
    parser.add_argument(
        "--huc-column", default="huc8",
        help="Column name to group bridges by (default: huc8)"
    )
    parser.add_argument(
        "--osmid-column", default="osmid",
        help="Column name for bridge OSM IDs (default: osmid)"
    )
    parser.add_argument(
        "--gpkg-template", default=DEFAULT_GPKG_TEMPLATE,
        help=f"Filename template for per-HUC GPKGs (default: {DEFAULT_GPKG_TEMPLATE})"
    )
    parser.add_argument(
        "--runs-dir", default="./data/runs",
        help="Root directory for runs (default: ./data/runs)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing run directory if it exists"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)

    run_dir = Path(args.runs_dir) / args.run_name
    if run_dir.exists() and not args.force:
        print(f"Error: run directory already exists: {run_dir}")
        print("Use --force to overwrite.")
        sys.exit(1)

    if run_dir.exists() and args.force:
        print(f"Removing existing run directory: {run_dir}")
        shutil.rmtree(run_dir)

    # Read and validate
    print(f"Reading {input_path}...")
    gdf = read_bridge_gpkg(
        input_path, required_cols=[args.huc_column, args.osmid_column]
    )
    total_bridges = len(gdf)
    unique_hucs = gdf[args.huc_column].nunique()
    print(f"  {total_bridges} bridges across {unique_hucs} HUC regions")

    # Create run directory structure
    input_dir = run_dir / "input"
    hucs_dir = run_dir / "hucs"
    source_dir = run_dir / "source"
    silver_dir = run_dir / "silver_training"
    predictions_dir = run_dir / "predictions"

    for d in [input_dir, hucs_dir, source_dir, silver_dir, predictions_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Copy input for reproducibility
    dest = input_dir / input_path.name
    shutil.copy2(input_path, dest)
    print(f"  Copied input to {dest}")

    # Split into per-HUC GPKGs
    print(f"Splitting by '{args.huc_column}' into {hucs_dir}/...")
    result = split_gpkg_by_column(
        gdf,
        column=args.huc_column,
        output_dir=hucs_dir,
        filename_template=args.gpkg_template,
        verbose=True,
    )
    print(f"  Created {len(result)} HUC directories")

    # Write run metadata
    config = {
        "run_name": args.run_name,
        "created": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_path.resolve()),
        "input_filename": input_path.name,
        "huc_column": args.huc_column,
        "osmid_column": args.osmid_column,
        "gpkg_template": args.gpkg_template,
        "total_bridges": total_bridges,
        "unique_hucs": unique_hucs,
    }
    config_path = run_dir / "run_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  Wrote {config_path}")

    # Summary
    print(f"\nRun prepared: {run_dir}")
    print(f"  Total bridges: {total_bridges}")
    print(f"  HUC regions:   {unique_hucs}")
    print(f"\nNext step — run weak supervision:")
    print(f"  python src/download_and_weak_supervise_hucs.py \\")
    print(f"      --hucs-dir {hucs_dir} \\")
    print(f"      --source-dir {source_dir} \\")
    print(f"      --silver-dir {silver_dir} \\")
    print(f"      --skip-existing \\")
    print(f"      --workers 8")


if __name__ == "__main__":
    main()
