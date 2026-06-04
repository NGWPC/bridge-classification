"""Tests for src/weak_supervision."""

import pytest
import numpy as np

ws = pytest.importorskip("src.weak_supervision", reason="weak_supervision not importable (requires sklearn+scipy+pdal)")

BridgeProcessingConfig = ws.BridgeProcessingConfig
check_bridge_linearity = ws.check_bridge_linearity
fit_ransac_from_arrays = ws.fit_ransac_from_arrays


@pytest.fixture
def default_config():
    return BridgeProcessingConfig()


def test_check_bridge_linearity_flat(default_config):
    """Flat bridge (points on a plane) should not be flagged as curved."""
    rng = np.random.default_rng(42)
    n = 200
    x = np.linspace(0, 20, n)
    y = rng.uniform(-2, 2, n)
    z = 0.1 * x + rng.normal(0, 0.05, n)
    xy = np.stack([x, y], axis=1)
    is_curved, deviation = check_bridge_linearity(xy, z, default_config)
    assert not is_curved
    assert deviation < default_config.linearity_deviation_threshold


def test_check_bridge_linearity_arched(default_config):
    """Arched bridge (parabolic Z profile) should be flagged as curved."""
    rng = np.random.default_rng(42)
    n = 200
    x = np.linspace(0, 20, n)
    y = rng.uniform(-2, 2, n)
    z = -0.1 * (x - 10) ** 2 + 10
    xy = np.stack([x, y], axis=1)
    is_curved, deviation = check_bridge_linearity(
        xy, z, default_config, deviation_threshold=default_config.linearity_final_deviation_threshold
    )
    assert is_curved
    assert deviation > default_config.linearity_final_deviation_threshold


def test_fit_ransac_from_arrays_planar(default_config):
    """Points on a known plane should produce a successful RANSAC fit."""
    rng = np.random.default_rng(42)
    n = 100
    x = rng.uniform(0, 10, n).astype(np.float64)
    y = rng.uniform(0, 10, n).astype(np.float64)
    z = (0.5 * x + 0.3 * y + 2.0 + rng.normal(0, 0.05, n)).astype(np.float64)
    classification = np.full(n, 2, dtype=np.int32)
    arrays = np.zeros(n, dtype=[('X', 'f8'), ('Y', 'f8'), ('Z', 'f8'), ('Classification', 'i4')])
    arrays['X'] = x
    arrays['Y'] = y
    arrays['Z'] = z
    arrays['Classification'] = classification
    result = fit_ransac_from_arrays(arrays, default_config)
    assert result['success']
    assert abs(result['coef_x'] - 0.5) < 0.15
    assert abs(result['coef_y'] - 0.3) < 0.15
