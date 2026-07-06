"""Model registry I/O for the S3-backed model registry.

Shared load/upload operations for registry.json, used by
register_model, promote_model, compare_experiments, and evaluate_model.
"""

import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.s3_client import download_json, object_exists, upload_json


def load_registry(s3_client: Any, bucket: str, registry_key: str) -> Dict[str, Any]:
    """Download registry.json from S3, or return a skeleton if it doesn't exist.

    Args:
        s3_client: Boto3 S3 client.
        bucket: S3 bucket containing the registry.
        registry_key: S3 key for registry.json.

    Returns:
        Registry dict with keys: schema_version, models, production.
    """
    if object_exists(s3_client, bucket, registry_key):
        return download_json(s3_client, bucket, registry_key)
    return {"schema_version": 1, "models": {}, "production": None}


def upload_registry(s3_client: Any, bucket: str, registry_key: str, registry: Dict[str, Any]) -> None:
    """Write registry.json to a temp file and upload to S3.

    Args:
        s3_client: Boto3 S3 client.
        bucket: S3 bucket containing the registry.
        registry_key: S3 key for registry.json.
        registry: Registry dict to upload.
    """
    upload_json(s3_client, registry, bucket, registry_key)
