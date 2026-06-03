"""GeoPackage I/O utilities for bridge data.

Shared read, write, split, and iteration helpers used across
the weak supervision pipeline, inference preparation, and analysis tools.
"""

from pathlib import Path
from typing import Dict, Iterator, Optional, Sequence, Tuple, Union

import geopandas as gpd

DEFAULT_GPKG_TEMPLATE = "osm_bridges_lidar_subset__{huc_id}.gpkg"


def read_bridge_gpkg(
    path: Union[str, Path],
    required_cols: Sequence[str] = ("osmid",),
    target_epsg: int = 3857,
) -> gpd.GeoDataFrame:
    """Read a bridge GeoPackage, validate columns, reproject, and cast osmid to str.

    Args:
        path: Path to the .gpkg file.
        required_cols: Columns that must be present. Raises ValueError if any are missing.
        target_epsg: Target CRS EPSG code. Default: 3857 (Web Mercator).

    Returns:
        GeoDataFrame reprojected to target_epsg with osmid as str (if present).
    """
    gdf = gpd.read_file(str(path))
    missing = [c for c in required_cols if c not in gdf.columns]
    if missing:
        raise ValueError(f"Missing required columns in {path}: {missing}")
    gdf = gdf.to_crs(epsg=target_epsg)
    if "osmid" in gdf.columns:
        gdf["osmid"] = gdf["osmid"].astype(str)
    return gdf


def write_gpkg(gdf: gpd.GeoDataFrame, path: Union[str, Path]) -> None:
    """Write a GeoDataFrame to a GeoPackage file, creating parent directories."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(str(path), driver="GPKG")


def split_gpkg_by_column(
    gdf: gpd.GeoDataFrame,
    column: str,
    output_dir: Union[str, Path],
    filename_template: str = DEFAULT_GPKG_TEMPLATE,
    verbose: bool = False,
) -> Dict[str, Path]:
    """Split a GeoDataFrame into per-value GeoPackage files.

    Groups by `column`, writes one GPKG per group into
    `{output_dir}/{value}/{filename_template}` where `{huc_id}` in the
    template is replaced by the group value.

    Args:
        gdf: Input GeoDataFrame.
        column: Column to group by.
        output_dir: Root output directory.
        filename_template: Filename with `{huc_id}` placeholder.
        verbose: Print progress every 200 groups.

    Returns:
        Dict mapping group values to written file paths.
    """
    output_dir = Path(output_dir)
    groups = gdf.groupby(column)
    total = len(groups)
    result = {}
    for i, (value, group_gdf) in enumerate(groups, 1):
        value_str = str(value)
        filename = filename_template.replace("{huc_id}", value_str)
        out_path = output_dir / value_str / filename
        write_gpkg(group_gdf, out_path)
        result[value_str] = out_path
        if verbose and (i % 200 == 0 or i == total):
            print(f"  {i}/{total} written", flush=True)
    return result


def iter_huc_gpkgs(
    hucs_dir: Union[str, Path],
    filename_template: str = DEFAULT_GPKG_TEMPLATE,
    huc_ids: Optional[Sequence[str]] = None,
) -> Iterator[Tuple[str, Path]]:
    """Yield (huc_id, gpkg_path) for each HUC directory containing a matching GPKG.

    Iterates subdirectories of hucs_dir in sorted order. Each subdirectory
    name is treated as a HUC ID. Directories without a matching GPKG file
    are silently skipped.

    Args:
        hucs_dir: Root directory containing per-HUC subdirectories.
        filename_template: GPKG filename with `{huc_id}` placeholder.
        huc_ids: Optional allowlist of HUC IDs to include.

    Yields:
        (huc_id, gpkg_path) tuples.
    """
    hucs_dir = Path(hucs_dir)
    huc_id_set = set(huc_ids) if huc_ids is not None else None
    for item in sorted(hucs_dir.iterdir()):
        if not item.is_dir():
            continue
        huc_id = item.name
        if huc_id_set is not None and huc_id not in huc_id_set:
            continue
        gpkg_file = item / filename_template.replace("{huc_id}", huc_id)
        if gpkg_file.exists():
            yield huc_id, gpkg_file


def filter_by_ids(
    gdf: gpd.GeoDataFrame,
    column: str,
    ids: Sequence,
) -> gpd.GeoDataFrame:
    """Filter a GeoDataFrame to rows where column value is in ids.

    Handles mixed types by casting both the column and the filter values
    to strings before comparison.

    Args:
        gdf: Input GeoDataFrame.
        column: Column to filter on.
        ids: Values to keep (will be cast to str).

    Returns:
        Filtered GeoDataFrame.
    """
    ids_str = [str(x) for x in ids]
    col_str = gdf[column].astype(str)
    return gdf[col_str.isin(ids_str)]
