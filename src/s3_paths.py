"""
Bridge-specific S3 path conventions for inference I/O.

Resolves manifest lines to full S3 keys by probing extensions,
and computes output key naming by inference mode (raw/masked/both).
"""

from pathlib import PurePosixPath
from typing import Any, Dict

from botocore.exceptions import ClientError

from src.constants import InferenceMode

PROBE_EXTENSIONS = ['.laz', '.las']


def resolve_input_key(s3_client: Any, bucket: str, input_prefix: str, manifest_line: str) -> str:
    """Resolve a manifest line to a full S3 input key, probing extensions if needed.

    If the manifest line already ends with .laz or .las, it is used directly.
    Otherwise each extension in PROBE_EXTENSIONS is tried via head_object.

    Args:
        s3_client: boto3 S3 client.
        bucket: S3 bucket name.
        input_prefix: S3 prefix for input files.
        manifest_line: e.g. '02050206/bridge_123' or '02050206/bridge_123.laz'

    Returns:
        Full S3 key string (e.g. 'prefix/02050206/bridge_123.laz').

    Raises:
        FileNotFoundError if no matching object exists in S3.
    """
    p = PurePosixPath(manifest_line)

    if p.suffix in ('.laz', '.las'):
        return f"{input_prefix}/{manifest_line}"

    for ext in PROBE_EXTENSIONS:
        key = f"{input_prefix}/{manifest_line}{ext}"
        try:
            s3_client.head_object(Bucket=bucket, Key=key)
            return key
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                continue
            raise

    raise FileNotFoundError(
        f"No file found in S3 for manifest line '{manifest_line}' "
        f"(tried extensions: {PROBE_EXTENSIONS})"
    )


def resolve_extension(s3_client: Any, bucket: str, input_prefix: str, manifest_line: str) -> str:
    """Determine the actual file extension for a manifest line by probing S3.

    Returns the extension from the manifest line directly if it already has one.
    Otherwise probes S3 via resolve_input_key. Falls back to '.laz' if not found.

    Args:
        s3_client: boto3 S3 client.
        bucket: S3 bucket name.
        input_prefix: S3 prefix for input files.
        manifest_line: Manifest entry.

    Returns:
        Extension string (e.g. '.laz').
    """
    p = PurePosixPath(manifest_line)
    if p.suffix in ('.laz', '.las'):
        return p.suffix
    try:
        key = resolve_input_key(s3_client, bucket, input_prefix, manifest_line)
        return PurePosixPath(key).suffix
    except FileNotFoundError:
        return '.laz'  # default fallback


def resolve_output_keys(output_prefix: str, manifest_line: str, ext: str, mode: InferenceMode) -> Dict[str, str]:
    """Compute the expected S3 output key(s) for a manifest line.

    Args:
        output_prefix: S3 prefix for output files (no trailing slash).
        manifest_line: Manifest entry used to derive HUC ID and stem
                       (e.g. '02050206/bridge_123' or '02050206/bridge_123.laz').
        ext: File extension to use for outputs (e.g. '.laz').
        mode: Inference mode - 'raw', 'masked', or 'both'.

    Returns:
        Dict with keys:
          'primary' - always present (the main output key)
          'masked'  - present only when mode='both'

    Output key patterns:
    - raw:     {output_prefix}/{huc_id}/{stem}_predicted{ext}
    - masked:  {output_prefix}/{huc_id}/{stem}_bridge_masked{ext}
    - both:    primary = {output_prefix}/{huc_id}/{stem}_predicted{ext}
               masked  = {output_prefix}/{huc_id}/{stem}_bridge_masked{ext}
    """
    p = PurePosixPath(manifest_line)
    huc_id = str(p.parent)
    stem = p.stem

    if mode == InferenceMode.MASKED:
        primary = f"{output_prefix}/{huc_id}/{stem}_bridge_masked{ext}"
    else:
        primary = f"{output_prefix}/{huc_id}/{stem}_predicted{ext}"

    result = {'primary': primary}

    if mode == InferenceMode.BOTH:
        result['masked'] = f"{output_prefix}/{huc_id}/{stem}_bridge_masked{ext}"

    return result
