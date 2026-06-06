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


class TestInferenceMode:
    def test_boundary_conversion(self):
        """Env vars and CLI args arrive as strings — enum must accept them."""
        from src.constants import InferenceMode
        assert InferenceMode("masked") == InferenceMode.MASKED
        assert InferenceMode("raw") == InferenceMode.RAW
        assert InferenceMode("both") == InferenceMode.BOTH

    def test_rejects_invalid_string(self):
        """Typo in INFERENCE_MODE env var must fail fast, not silently produce wrong S3 paths."""
        from src.constants import InferenceMode
        with pytest.raises(ValueError):
            InferenceMode("masking")
