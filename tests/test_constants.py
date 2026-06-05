"""Tests for src/constants.py — mapping consistency and class schema."""

import signal

import pytest

from src.constants import (
    LAS_TO_MODEL_MAP,
    MODEL_TO_LAS_MAP,
    NUM_CLASSES,
    BRIDGE_DECK_ASPRS_CODE,
    BRIDGE_DECK_MODEL_CLASS,
    OBSTACLES_ASPRS_CODE,
    OBSTACLES_MODEL_CLASS,
    BridgeTimeout,
    _timeout_handler,
)


class TestMappingConsistency:
    def test_covers_all_model_classes(self):
        for c in range(NUM_CLASSES):
            assert c in MODEL_TO_LAS_MAP, f"Model class {c} missing from MODEL_TO_LAS_MAP"

    def test_bridge_deck_roundtrip(self):
        """ASPRS 17 -> model class -> ASPRS 17 must be lossless."""
        model_class = LAS_TO_MODEL_MAP[17]
        assert model_class == BRIDGE_DECK_MODEL_CLASS
        assert MODEL_TO_LAS_MAP[model_class] == BRIDGE_DECK_ASPRS_CODE

    def test_obstacles_roundtrip(self):
        """ASPRS 18 -> model class -> ASPRS 18 must be lossless."""
        model_class = LAS_TO_MODEL_MAP[18]
        assert model_class == OBSTACLES_MODEL_CLASS
        assert MODEL_TO_LAS_MAP[model_class] == OBSTACLES_ASPRS_CODE


class TestTimeoutMachinery:
    def test_timeout_handler_raises(self):
        with pytest.raises(BridgeTimeout):
            _timeout_handler(signal.SIGALRM, None)


class TestTimeoutSentinel:
    def test_timeout_sentinel_written_and_skipped(self, tmp_path):
        """Once a timeout sentinel is written, timeout_sentinel_exists returns True."""
        pytest.importorskip("geopandas")
        from src.download_and_weak_supervise_hucs import DataManager
        dm = DataManager(str(tmp_path / "source"), str(tmp_path / "silver"))
        assert not dm.timeout_sentinel_exists("huc01", "12345", "SomeSource_2020")
        dm.write_timeout_sentinel("huc01", "12345", "SomeSource_2020")
        assert dm.timeout_sentinel_exists("huc01", "12345", "SomeSource_2020")
