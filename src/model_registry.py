"""Model registry I/O for the S3-backed model registry.

Shared load/upload operations for registry.json, used by
register_model, promote_model, compare_experiments, and evaluate_model.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.s3 import download_file, object_exists, upload_file


def load_registry(s3_client, bucket, registry_key):
    """Download registry.json from S3, or return a skeleton if it doesn't exist."""
    if object_exists(s3_client, bucket, registry_key):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            download_file(s3_client, bucket, registry_key, tmp_path)
            with open(tmp_path) as f:
                return json.load(f)
        finally:
            os.unlink(tmp_path)
    return {"schema_version": 1, "models": {}, "production": None}


def upload_registry(s3_client, bucket, registry_key, registry):
    """Write registry.json to a temp file and upload to S3."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(registry, tmp, indent=2)
        tmp_path = tmp.name
    try:
        upload_file(s3_client, tmp_path, bucket, registry_key)
    finally:
        os.unlink(tmp_path)
