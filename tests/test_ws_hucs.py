"""Tests for src/download_and_weak_supervise_hucs.py — sentinel files and subprocess timeout."""

import multiprocessing
import time

import pytest


def _sleep_forever(result_queue, *args):
    """Subprocess target that hangs indefinitely (simulates stuck PDAL)."""
    time.sleep(9999)


def _worker_spawn_and_timeout(_):
    """Pool worker task: spawn a child subprocess, wait 1s, kill it.

    Must be module-level (not nested) for pickling with spawn start method.
    """
    from src.weak_supervision import FailureReason
    q = multiprocessing.Queue(maxsize=1)
    p = multiprocessing.Process(target=_sleep_forever, args=(q,))
    p.start()
    p.join(timeout=1)
    if p.is_alive():
        p.terminate()
        p.join(5)
        return {'success': False, 'reason': FailureReason.TIMEOUT}
    return {'success': True}


class TestTimeoutSentinel:
    def test_timeout_sentinel_written_and_skipped(self, tmp_path):
        """Once a timeout sentinel is written, timeout_sentinel_exists returns True."""
        pytest.importorskip("geopandas")
        from src.download_and_weak_supervise_hucs import DataManager
        dm = DataManager(str(tmp_path / "source"), str(tmp_path / "silver"))
        assert not dm.timeout_sentinel_exists("huc01", "12345", "SomeSource_2020")
        dm.write_timeout_sentinel("huc01", "12345", "SomeSource_2020")
        assert dm.timeout_sentinel_exists("huc01", "12345", "SomeSource_2020")


class TestSubprocessTimeout:
    def test_pool_worker_can_spawn_and_timeout_subprocess(self):
        """Non-daemonic pool workers can spawn child processes and kill them on timeout.

        Regression test: standard multiprocessing.Pool uses daemonic workers
        that raise 'daemonic processes are not allowed to have children'.
        _NoDaemonPool fixes this. This test verifies the full pattern:
        pool worker spawns child, child hangs, worker kills it after timeout.
        """
        pytest.importorskip("geopandas")
        from src.download_and_weak_supervise_hucs import _NoDaemonPool
        from src.weak_supervision import FailureReason

        with _NoDaemonPool(processes=1) as pool:
            result = pool.apply(_worker_spawn_and_timeout, (None,))

        assert result['success'] is False
        assert result['reason'] == FailureReason.TIMEOUT
