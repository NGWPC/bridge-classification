"""Tests for src/gpkg_utils shared GeoPackage utilities."""

import pytest

pd = pytest.importorskip("pandas", reason="pandas not installed")
gpd = pytest.importorskip("geopandas", reason="geopandas not installed")

from shapely.geometry import LineString
from src.gpkg_utils import read_bridge_gpkg, write_gpkg, split_gpkg_by_column, iter_huc_gpkgs, filter_by_ids


@pytest.fixture
def sample_bridge_gpkg(tmp_path):
    """Write a minimal bridge GPKG with osmid, name, geometry."""
    gdf = gpd.GeoDataFrame(
        {
            "osmid": [123, 456],
            "name": ["Bridge A", "Bridge B"],
        },
        geometry=[
            LineString([(0, 0), (1, 1)]),
            LineString([(2, 2), (3, 3)]),
        ],
        crs="EPSG:4326",
    )
    path = tmp_path / "bridges.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


def test_read_bridge_gpkg_basic(sample_bridge_gpkg):
    gdf = read_bridge_gpkg(sample_bridge_gpkg)
    assert len(gdf) == 2
    assert gdf.crs.to_epsg() == 3857
    assert pd.api.types.is_string_dtype(gdf["osmid"])


def test_read_bridge_gpkg_missing_required_col(sample_bridge_gpkg):
    with pytest.raises(ValueError, match="huc8"):
        read_bridge_gpkg(sample_bridge_gpkg, required_cols=("osmid", "huc8"))


def test_read_bridge_gpkg_no_required_cols(sample_bridge_gpkg):
    gdf = read_bridge_gpkg(sample_bridge_gpkg, required_cols=())
    assert len(gdf) == 2


@pytest.fixture
def multi_huc_gdf():
    """GeoDataFrame with bridges across 3 HUC8s."""
    return gpd.GeoDataFrame(
        {
            "osmid": ["1", "2", "3", "4", "5"],
            "huc8": ["01010001", "01010001", "01010002", "01010002", "01010003"],
            "name": ["A", "B", "C", "D", "E"],
        },
        geometry=[
            LineString([(i, 0), (i + 1, 1)]) for i in range(5)
        ],
        crs="EPSG:3857",
    )


def test_write_gpkg_creates_file(tmp_path, multi_huc_gdf):
    out = tmp_path / "sub" / "nested" / "output.gpkg"
    write_gpkg(multi_huc_gdf, out)
    assert out.exists()
    result = gpd.read_file(out)
    assert len(result) == 5


def test_split_gpkg_by_column(tmp_path, multi_huc_gdf):
    result = split_gpkg_by_column(
        multi_huc_gdf,
        column="huc8",
        output_dir=tmp_path,
        filename_template="bridges__{huc_id}.gpkg",
    )
    assert len(result) == 3
    assert (tmp_path / "01010001" / "bridges__01010001.gpkg").exists()
    assert (tmp_path / "01010002" / "bridges__01010002.gpkg").exists()
    assert (tmp_path / "01010003" / "bridges__01010003.gpkg").exists()

    gdf_1 = gpd.read_file(result["01010001"])
    assert len(gdf_1) == 2
    gdf_3 = gpd.read_file(result["01010003"])
    assert len(gdf_3) == 1


@pytest.fixture
def huc_dir_tree(tmp_path, multi_huc_gdf):
    """Create a realistic HUC directory tree with GPKG files."""
    split_gpkg_by_column(
        multi_huc_gdf,
        column="huc8",
        output_dir=tmp_path,
        filename_template="osm_bridges_lidar_subset__{huc_id}.gpkg",
    )
    # Add a non-HUC file to test filtering
    (tmp_path / "README.md").write_text("ignore me")
    return tmp_path


def test_iter_huc_gpkgs_finds_all(huc_dir_tree):
    pairs = list(iter_huc_gpkgs(huc_dir_tree))
    assert len(pairs) == 3
    huc_ids = [huc_id for huc_id, _ in pairs]
    assert huc_ids == ["01010001", "01010002", "01010003"]  # sorted


def test_iter_huc_gpkgs_filter_by_huc_ids(huc_dir_tree):
    pairs = list(iter_huc_gpkgs(huc_dir_tree, huc_ids=["01010001", "01010003"]))
    assert len(pairs) == 2
    huc_ids = [huc_id for huc_id, _ in pairs]
    assert "01010002" not in huc_ids


def test_iter_huc_gpkgs_custom_template(tmp_path, multi_huc_gdf):
    split_gpkg_by_column(
        multi_huc_gdf,
        column="huc8",
        output_dir=tmp_path,
        filename_template="custom__{huc_id}.gpkg",
    )
    pairs = list(iter_huc_gpkgs(
        tmp_path, filename_template="custom__{huc_id}.gpkg"
    ))
    assert len(pairs) == 3


def test_iter_huc_gpkgs_missing_gpkg_skipped(huc_dir_tree):
    gpkg_path = huc_dir_tree / "01010002" / "osm_bridges_lidar_subset__01010002.gpkg"
    gpkg_path.unlink()
    pairs = list(iter_huc_gpkgs(huc_dir_tree))
    assert len(pairs) == 2


def test_filter_by_ids(multi_huc_gdf):
    result = filter_by_ids(multi_huc_gdf, "osmid", ["1", "3", "999"])
    assert len(result) == 2
    assert set(result["osmid"]) == {"1", "3"}


def test_filter_by_ids_int_input(multi_huc_gdf):
    result = filter_by_ids(multi_huc_gdf, "osmid", [1, 3])
    assert len(result) == 2


def test_filter_by_ids_empty(multi_huc_gdf):
    result = filter_by_ids(multi_huc_gdf, "osmid", [])
    assert len(result) == 0
