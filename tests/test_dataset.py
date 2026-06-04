"""Tests for src/dataset — BridgeDataset and sparse_collate_fn."""

import pytest
import numpy as np

ds = pytest.importorskip("src.dataset", reason="src.dataset not importable (requires torch)")

BridgeDataset = ds.BridgeDataset
sparse_collate_fn = ds.sparse_collate_fn


@pytest.fixture
def synthetic_npy_dir(tmp_path):
    """Create a directory with one synthetic .npy file (N x 5: x,y,z,intensity,label)."""
    rng = np.random.default_rng(42)
    n = 50
    xyz = rng.uniform(0, 5, (n, 3)).astype(np.float32)
    intensity = rng.uniform(0, 1, (n, 1)).astype(np.float32)
    labels = rng.choice([0, 1, 2], n).reshape(-1, 1).astype(np.float32)
    data = np.hstack([xyz, intensity, labels])
    np.save(tmp_path / "bridge_test.npy", data)
    return tmp_path


def test_bridge_dataset_getitem(synthetic_npy_dir):
    """BridgeDataset loads a .npy file and returns voxelized (coords, features, labels)."""
    ds = BridgeDataset(str(synthetic_npy_dir), voxel_size=1.0, augment=False)
    assert len(ds) == 1
    coords, features, labels = ds[0]
    assert coords.ndim == 2 and coords.shape[1] == 3
    assert features.ndim == 2 and features.shape[1] == 1
    assert labels.ndim == 1
    assert len(coords) == len(features) == len(labels)
    assert coords.dtype == np.int32 or coords.dtype == np.int64


def test_sparse_collate_fn_batch_structure():
    """sparse_collate_fn prepends batch_id and produces correct dict structure."""
    sample_a = (
        np.array([[0, 0, 0], [1, 1, 1]], dtype=np.int32),
        np.array([[0.5], [0.8]], dtype=np.float32),
        np.array([1, 2], dtype=np.int64),
    )
    sample_b = (
        np.array([[2, 2, 2]], dtype=np.int32),
        np.array([[0.3]], dtype=np.float32),
        np.array([0], dtype=np.int64),
    )
    result = sparse_collate_fn([sample_a, sample_b])
    assert set(result.keys()) == {"coordinates", "features", "labels", "sample_voxel_counts"}
    assert result["coordinates"].shape == (3, 4)  # 2+1 voxels, 4 cols (batch_id, x, y, z)
    assert result["coordinates"][0, 0] == 0  # first sample batch_id=0
    assert result["coordinates"][2, 0] == 1  # second sample batch_id=1
    assert result["features"].shape == (3, 1)
    assert result["labels"].shape == (3,)
    assert result["sample_voxel_counts"] == [2, 1]
