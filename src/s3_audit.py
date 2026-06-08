"""S3 output audit for bridge inference runs.

Thread-pool orchestrator that checks whether expected output files exist in S3.
Uses bridge path conventions from s3_paths and generic S3 ops from s3_client.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from src.constants import InferenceMode
from src.s3_client import create_s3_client, object_exists
from src.s3_paths import resolve_extension, resolve_output_keys

DEFAULT_AUDIT_WORKERS = 200


def audit_s3_outputs(
    profile: Optional[str],
    bucket: str,
    input_prefix: str,
    output_prefix: str,
    mode: InferenceMode,
    manifest_lines: List[str],
    workers: int = DEFAULT_AUDIT_WORKERS,
    progress_interval: int = 0,
) -> Tuple[int, List[str]]:
    """Check S3 for expected inference outputs using a thread pool.

    Creates per-thread S3 clients (boto3 clients are not thread-safe).
    For each manifest line, resolves the expected output key(s) and checks
    existence via head_object.

    Args:
        profile: AWS profile name (None uses default credentials).
        bucket: S3 bucket containing outputs.
        input_prefix: S3 prefix for input files (for extension probing).
            Empty string skips probing and assumes .laz.
        output_prefix: S3 prefix for output files.
        mode: Inference mode (determines expected output filenames).
        manifest_lines: List of manifest entries to check.
        workers: Number of parallel threads.
        progress_interval: Print progress every N entries (0 = silent).

    Returns:
        Tuple of (found_count, list of missing manifest lines).
    """
    thread_local = threading.local()
    found = 0
    missing: List[str] = []
    completed = 0
    lock = threading.Lock()

    def _check_one(line: str) -> Tuple[str, bool]:
        if not hasattr(thread_local, 's3'):
            thread_local.s3 = create_s3_client(profile)
        s3 = thread_local.s3
        ext = resolve_extension(s3, bucket, input_prefix, line) if input_prefix else '.laz'
        output_keys = resolve_output_keys(output_prefix, line, ext, mode)
        all_exist = all(object_exists(s3, bucket, k) for k in output_keys.values())
        return line, all_exist

    total = len(manifest_lines)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_check_one, line): line for line in manifest_lines}
        for future in as_completed(futures):
            line, exists = future.result()
            with lock:
                if exists:
                    found += 1
                else:
                    missing.append(line)
                completed += 1
                if progress_interval > 0 and completed % progress_interval == 0:
                    print(f"  Checked {completed}/{total} — {found} found, {len(missing)} missing")

    return found, missing
