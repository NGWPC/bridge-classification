"""Tests for utils/calculate_weights.py — weight computation and JSON loading."""

import json
import pytest

from utils.calculate_weights import _load_one_json, compute_weights


class TestComputeWeights:
    def test_imbalanced_distribution(self):
        """Rare classes get higher weights. W_c = total / (n_classes * count_c)."""
        counts = {0: 1000, 1: 100, 2: 50, 3: 10}
        weights = compute_weights(counts, n_classes=4)
        assert len(weights) == 4
        assert weights[0] < weights[1] < weights[2] < weights[3]
        # class 2 has 20x fewer points than class 0 → 20x higher weight
        assert weights[2] / weights[0] == pytest.approx(20.0, abs=0.1)


class TestLoadOneJson:
    def test_valid_json_returns_counts(self, tmp_path):
        meta = {"class_distribution": {"0": 500, "1": 300, "2": 150, "3": 50}}
        path = tmp_path / "bridge.json"
        path.write_text(json.dumps(meta))

        counts, err = _load_one_json(path)
        assert err is None
        assert counts == {0: 500, 1: 300, 2: 150, 3: 50}

    def test_missing_class_distribution_returns_empty(self, tmp_path):
        """JSON without class_distribution key -> empty dict, no error path."""
        meta = {"original_file": "bridge.laz"}
        path = tmp_path / "bridge.json"
        path.write_text(json.dumps(meta))

        counts, err = _load_one_json(path)
        assert err is None
        assert counts == {}
