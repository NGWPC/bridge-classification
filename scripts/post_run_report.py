"""
Bridge Classification — Post-Run Report

Generates a comprehensive report after an AWS Batch inference run completes.
Reads _run_config.json (saved at submission), audits S3 outputs, queries
CloudWatch logs for per-child summaries and per-bridge timing, and saves
_run_report.json to the output prefix.

Usage:
    python scripts/post_run_report.py \
        --bucket fimc-data \
        --output-prefix bridge-classification/runs/noaa-bridges-without-tif/predictions \
        --mode masked \
        --profile data

    # With explicit input prefix (for S3 extension probing during audit):
    python scripts/post_run_report.py \
        --bucket fimc-data \
        --output-prefix bridge-classification/runs/.../predictions \
        --input-prefix bridge-classification/runs/.../source \
        --mode masked \
        --profile data
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Tuple

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.constants import InferenceMode
from src.s3_audit import audit_s3_outputs
from src.s3_client import (
    create_s3_client, download_json, stream_manifest_lines,
    upload_json, upload_text,
)


SUMMARY_PATTERN = re.compile(
    r'SUMMARY succeeded=(\d+) failed=(\d+) skipped_exists=(\d+) '
    r'skipped_too_few_points=(\d+) download_failed=(\d+) total=(\d+) '
    r'wall_clock_seconds=([\d.]+) wall_clock_hours=([\d.]+)'
)

BRIDGE_TIME_PATTERN = re.compile(r'bridge_seconds=([\d.]+)s')

LOG_GROUP = '/aws/batch/bridge-classifier'
DEFAULT_AUDIT_WORKERS = 200  # must match src/s3_audit.py default



def describe_batch_job(batch_client: Any, job_id: str) -> Dict[str, Any]:
    """Get job status and timing from AWS Batch."""
    response = batch_client.describe_jobs(jobs=[job_id])
    if not response['jobs']:
        return {'status': 'NOT_FOUND'}
    job = response['jobs'][0]
    result = {
        'status': job.get('status', 'UNKNOWN'),
        'status_reason': job.get('statusReason', ''),
    }
    if 'createdAt' in job:
        result['created_at'] = datetime.fromtimestamp(job['createdAt'] / 1000, tz=timezone.utc).isoformat()
    if 'startedAt' in job:
        result['started_at'] = datetime.fromtimestamp(job['startedAt'] / 1000, tz=timezone.utc).isoformat()
    if 'stoppedAt' in job:
        result['stopped_at'] = datetime.fromtimestamp(job['stoppedAt'] / 1000, tz=timezone.utc).isoformat()
        if 'startedAt' in job:
            result['wall_clock_hours'] = round((job['stoppedAt'] - job['startedAt']) / 1000 / 3600, 2)
    if 'arrayProperties' in job:
        result['array_size'] = job['arrayProperties'].get('size', 0)
    return result


def _query_cloudwatch(
    logs_client: Any,
    filter_pattern: str,
    start_ms: int,
    end_ms: int,
    processor: Callable[[str], None],
) -> None:
    """Paginate CloudWatch filter_log_events calls, passing each message to processor."""
    kwargs = {
        'logGroupName': LOG_GROUP,
        'startTime': start_ms,
        'endTime': end_ms + 60_000,
        'filterPattern': filter_pattern,
    }
    while True:
        response = logs_client.filter_log_events(**kwargs)
        for event in response.get('events', []):
            processor(event['message'])
        if 'nextToken' not in response:
            break
        kwargs['nextToken'] = response['nextToken']


def query_cloudwatch_summaries(
    logs_client: Any, start_ms: int, end_ms: int
) -> Tuple[Dict[str, int], List[float]]:
    """Query CloudWatch for SUMMARY lines, return aggregated totals and per-child wall clock hours."""
    totals = {
        'succeeded': 0, 'failed': 0, 'skipped_exists': 0,
        'skipped_too_few_points': 0, 'download_failed': 0, 'total': 0,
    }
    child_hours: List[float] = []

    def process(msg: str) -> None:
        match = SUMMARY_PATTERN.search(msg)
        if match:
            totals['succeeded'] += int(match.group(1))
            totals['failed'] += int(match.group(2))
            totals['skipped_exists'] += int(match.group(3))
            totals['skipped_too_few_points'] += int(match.group(4))
            totals['download_failed'] += int(match.group(5))
            totals['total'] += int(match.group(6))
            child_hours.append(float(match.group(8)))

    _query_cloudwatch(logs_client, 'SUMMARY', start_ms, end_ms, process)
    return totals, child_hours


def query_cloudwatch_bridge_times(
    logs_client: Any, start_ms: int, end_ms: int
) -> List[float]:
    """Query CloudWatch for INFER_OK lines, extract per-bridge seconds."""
    times: List[float] = []

    def process(msg: str) -> None:
        match = BRIDGE_TIME_PATTERN.search(msg)
        if match:
            times.append(float(match.group(1)))

    _query_cloudwatch(logs_client, 'INFER_OK', start_ms, end_ms, process)
    return times


def compute_percentile(values: List[float], pct: float) -> float:
    """Compute percentile from sorted values."""
    if not values:
        return 0.0
    values_sorted = sorted(values)
    idx = int(len(values_sorted) * pct / 100)
    idx = min(idx, len(values_sorted) - 1)
    return values_sorted[idx]


def main() -> None:
    parser = argparse.ArgumentParser(description='Bridge Classification — Post-Run Report')
    parser.add_argument('--bucket', type=str, required=True, help='S3 bucket')
    parser.add_argument('--output-prefix', type=str, required=True, help='S3 output prefix (where predictions are)')
    parser.add_argument('--input-prefix', type=str, default='', help='S3 input prefix (for extension probing during audit)')
    parser.add_argument('--mode', type=InferenceMode, default=InferenceMode.MASKED,
                        choices=[m.value for m in InferenceMode],
                        help='Inference mode (determines expected output filenames)')
    parser.add_argument('--audit-workers', type=int, default=DEFAULT_AUDIT_WORKERS,
                        help=f'Parallel S3 audit workers (default: {DEFAULT_AUDIT_WORKERS})')
    parser.add_argument('--skip-timing', action='store_true',
                        help='Skip per-bridge timing extraction (faster, fewer CloudWatch queries)')
    parser.add_argument('--region', type=str, default='us-east-1',
                        help='AWS region for Batch and CloudWatch (default: us-east-1)')
    parser.add_argument('--profile', type=str, help='AWS profile')
    args = parser.parse_args()

    s3 = create_s3_client(args.profile)

    # --- 1. Load run config ---
    print("Loading run config from S3...")
    try:
        config_key = f"{args.output_prefix}/_run_config.json"
        run_config = download_json(s3, args.bucket, config_key)
    except Exception as e:
        print(f"ERROR: Could not load _run_config.json: {e}")
        print("Was --bucket and --output-prefix passed to submit_batch_job.py?")
        sys.exit(1)

    job_id = run_config.get('job_id')
    manifest_uri = run_config.get('manifest_uri')
    expected_array_size = run_config.get('array_size', 0)
    print(f"Job: {run_config.get('job_name')} (ID: {job_id})")
    print(f"Manifest: {manifest_uri}")
    print(f"Total bridges: {run_config.get('total_bridges')}")

    # --- 2. Check job status ---
    print("\nChecking job status...")
    session = boto3.Session(profile_name=args.profile)
    batch_client = session.client('batch', region_name=args.region)
    job_info = describe_batch_job(batch_client, job_id)
    print(f"Status: {job_info['status']}")
    if 'wall_clock_hours' in job_info:
        print(f"Wall clock: {job_info['wall_clock_hours']} hours")

    # --- 3. Audit outputs ---
    print("\nAuditing S3 outputs...")
    manifest_lines = list(stream_manifest_lines(s3, manifest_uri))
    print(f"Manifest lines: {len(manifest_lines)}")

    found, missing = audit_s3_outputs(
        profile=args.profile,
        bucket=args.bucket,
        input_prefix=args.input_prefix,
        output_prefix=args.output_prefix,
        mode=args.mode,
        manifest_lines=manifest_lines,
        workers=args.audit_workers,
    )
    print(f"Found: {found}, Missing: {len(missing)}")

    # --- 4. Query CloudWatch ---
    logs_client = session.client('logs', region_name=args.region)

    totals = {}
    child_hours: List[float] = []
    timing = {}

    if 'started_at' in job_info:
        start_ms = int(datetime.fromisoformat(job_info['started_at']).timestamp() * 1000)
        end_ms = int(datetime.fromisoformat(job_info.get('stopped_at', job_info['started_at'])).timestamp() * 1000)

        print("\nQuerying CloudWatch for SUMMARY lines...")
        totals, child_hours = query_cloudwatch_summaries(logs_client, start_ms, end_ms)
        summary_count = len(child_hours)
        print(f"Found {summary_count} child summaries (expected {expected_array_size})")
        if summary_count < expected_array_size:
            print(f"WARNING: {expected_array_size - summary_count} children did not log SUMMARY (possible SPOT interruption)")

        print(f"Aggregated: succeeded={totals['succeeded']}, failed={totals['failed']}, "
              f"skipped_exists={totals['skipped_exists']}, "
              f"skipped_too_few_points={totals['skipped_too_few_points']}, "
              f"download_failed={totals['download_failed']}")

        if not args.skip_timing:
            print("\nQuerying CloudWatch for per-bridge timing (this may take ~30s)...")
            bridge_times = query_cloudwatch_bridge_times(logs_client, start_ms, end_ms)
            if bridge_times:
                timing = {
                    'bridges_timed': len(bridge_times),
                    'avg_seconds': round(sum(bridge_times) / len(bridge_times), 1),
                    'p50_seconds': round(compute_percentile(bridge_times, 50), 1),
                    'p95_seconds': round(compute_percentile(bridge_times, 95), 1),
                    'min_seconds': round(min(bridge_times), 1),
                    'max_seconds': round(max(bridge_times), 1),
                }
                print(f"Per-bridge: avg={timing['avg_seconds']}s, "
                      f"p50={timing['p50_seconds']}s, p95={timing['p95_seconds']}s")
        else:
            print("\nSkipping per-bridge timing (--skip-timing)")
    else:
        print("\nWARNING: Job has no start time — skipping CloudWatch queries")

    # --- 5. Build report ---
    report = {
        'reported_at': datetime.now(timezone.utc).isoformat(),
        'job': job_info,
        'audit': {
            'total': len(manifest_lines),
            'found': found,
            'missing': len(missing),
        },
        'aggregated_results': totals,
        'child_timing': {
            'children_reported': len(child_hours),
            'children_expected': expected_array_size,
            'min_hours': round(min(child_hours), 2) if child_hours else None,
            'max_hours': round(max(child_hours), 2) if child_hours else None,
            'avg_hours': round(sum(child_hours) / len(child_hours), 2) if child_hours else None,
        },
        'bridge_timing': timing,
        'run_config': run_config,
    }

    if missing:
        report['missing_entries'] = missing[:1000]
        if len(missing) > 1000:
            report['missing_entries_truncated'] = True
            report['total_missing'] = len(missing)

    # --- 6. Save report to S3 ---
    report_key = f"{args.output_prefix}/_run_report.json"
    upload_json(s3, report, args.bucket, report_key)
    print(f"\nReport saved: s3://{args.bucket}/{report_key}")

    # --- 7. Save missing manifest ---
    if missing:
        missing_key = f"{args.output_prefix}/_missing.txt"
        missing_text = "\n".join(missing) + "\n"
        upload_text(s3, missing_text, args.bucket, missing_key)
        print(f"Missing manifest: s3://{args.bucket}/{missing_key} ({len(missing)} entries)")

    # --- 8. Print summary ---
    print(f"\n{'='*60}")
    print(f"POST-RUN REPORT")
    print(f"{'='*60}")
    print(f"Job:        {run_config.get('job_name')}")
    print(f"Status:     {job_info['status']}")
    if 'wall_clock_hours' in job_info:
        print(f"Duration:   {job_info['wall_clock_hours']} hours")
    print(f"Audit:      {found} found, {len(missing)} missing out of {len(manifest_lines)}")
    if totals:
        print(f"Results:    {totals['succeeded']} succeeded, {totals['failed']} failed, "
              f"{totals['skipped_too_few_points']} skipped")
    if timing:
        print(f"Timing:     avg={timing['avg_seconds']}s, p50={timing['p50_seconds']}s, p95={timing['p95_seconds']}s")
    print(f"Report:     s3://{args.bucket}/{report_key}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
