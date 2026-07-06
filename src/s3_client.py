"""
Generic S3 operations - client factory, file I/O, URI parsing.

Pure S3 logic, no domain-specific code (e.g. no LAS/point cloud handling here).
"""

import json
import os
import tempfile
from typing import Any, Iterator, Optional, Tuple

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from src.constants import AWS_MAX_RETRIES


def create_s3_client(profile: Optional[str] = None) -> Any:
    """Create a boto3 S3 client with standard retry config.

    Args:
        profile: AWS profile name (None uses default credentials).

    Returns:
        boto3 S3 client with adaptive retry (AWS_MAX_RETRIES attempts).
    """
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.client('s3', config=BotoConfig(
        retries={'max_attempts': AWS_MAX_RETRIES, 'mode': 'adaptive'}
    ))


def parse_s3_uri(uri: str) -> Tuple[str, str]:
    """Split 's3://bucket/key' into (bucket, key)."""
    path = uri[5:]  # strip 's3://'
    bucket, _, key = path.partition('/')
    return bucket, key


def object_exists(s3_client: Any, bucket: str, key: str) -> bool:
    """Return True if the S3 object exists, False on 404; re-raises other errors."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise


def download_file(s3_client: Any, bucket: str, key: str, local_path: str) -> None:
    """Download an S3 object to a local path, creating parent directories as needed."""
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    s3_client.download_file(bucket, key, local_path)


def upload_file(s3_client: Any, local_path: str, bucket: str, key: str) -> None:
    """Upload a local file to S3."""
    s3_client.upload_file(local_path, bucket, key)


def upload_json(s3_client: Any, data: Any, bucket: str, key: str) -> None:
    """Serialize data as JSON and upload to S3 via temp file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
        json.dump(data, tmp, indent=2, default=str)
        tmp_path = tmp.name
    try:
        upload_file(s3_client, tmp_path, bucket, key)
    finally:
        os.unlink(tmp_path)


def upload_text(s3_client: Any, text: str, bucket: str, key: str) -> None:
    """Upload a text string to S3 via temp file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    try:
        upload_file(s3_client, tmp_path, bucket, key)
    finally:
        os.unlink(tmp_path)


def download_json(s3_client: Any, bucket: str, key: str) -> Any:
    """Download a JSON file from S3 and return parsed data."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        download_file(s3_client, bucket, key, tmp_path)
        with open(tmp_path) as f:
            return json.load(f)
    finally:
        os.unlink(tmp_path)


def stream_manifest_lines(s3_client: Any, manifest_uri: str) -> Iterator[str]:
    """Stream a manifest file from S3, yielding non-empty stripped lines.

    Args:
        s3_client: boto3 S3 client.
        manifest_uri: Full S3 URI (s3://bucket/key).

    Yields:
        Non-empty stripped line strings.
    """
    bucket, key = parse_s3_uri(manifest_uri)
    response = s3_client.get_object(Bucket=bucket, Key=key)
    for raw_line in response['Body'].iter_lines():
        line = raw_line.decode('utf-8').strip() if isinstance(raw_line, bytes) else raw_line.strip()
        if line:
            yield line
