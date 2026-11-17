"""@description 파일 잠금의 스레드·프로세스 동기화 동작 검증"""

from __future__ import annotations

import multiprocessing
import os
import threading
import time
from pathlib import Path

import pytest

from csat_benchmark.file_lock import FileLockTimeout, file_lock


def _hold_file_lock(path: str, started, release) -> None:
    """@description 자식 프로세스에서 파일 잠금을 유지하고 해제 신호 대기"""
    with file_lock(path, timeout=5):
        started.set()
        if not release.wait(20):
            raise TimeoutError("부모 프로세스의 해제 신호를 기다리다 시간이 초과되었습니다.")


def _race_first_file_lock(path: str, barrier, acquired) -> None:
    """@description 여러 프로세스의 첫 잠금 획득 경합 참가"""
    barrier.wait(timeout=10)
    with file_lock(path, timeout=5):
        acquired.put(True)
        time.sleep(0.05)


def test_file_lock_is_reentrant_in_same_thread(tmp_path: Path) -> None:
    target = tmp_path / "results.json"

    with file_lock(target):
        with file_lock(target, timeout=0):
            assert target.with_name("results.json.csat.lock").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows 경로 대소문자 정규화 검증")
def test_file_lock_is_reentrant_for_differently_cased_windows_path(tmp_path: Path) -> None:
    target = tmp_path / "results.json"

    with file_lock(target):
        with file_lock(str(target).upper(), timeout=0):
            pass


def test_another_thread_waits_until_release(tmp_path: Path) -> None:
    target = tmp_path / "results.json"
    attempting = threading.Event()
    acquired = threading.Event()

    def _wait_for_lock() -> None:
        attempting.set()
        with file_lock(target, timeout=2):
            acquired.set()

    with file_lock(target):
        thread = threading.Thread(target=_wait_for_lock)
        thread.start()
        assert attempting.wait(2)
        time.sleep(0.1)
        assert not acquired.is_set()

    thread.join(timeout=2)
    assert not thread.is_alive()
    assert acquired.is_set()


def test_another_process_blocks_until_release(tmp_path: Path) -> None:
    target = tmp_path / "results.json"
    context = multiprocessing.get_context("spawn")
    started = context.Event()
    release = context.Event()
    process = context.Process(target=_hold_file_lock, args=(str(target), started, release))
    process.start()

    try:
        assert started.wait(10)
        with pytest.raises(FileLockTimeout) as error:
            with file_lock(target, timeout=0.15):
                pytest.fail("자식 프로세스가 잠금을 보유하는 동안 부모가 잠금을 획득했습니다.")
        assert str(target.resolve()) + ".csat.lock" in str(error.value)
        assert "0.15" in str(error.value)

        release.set()
        process.join(timeout=10)
        assert not process.is_alive()
        assert process.exitcode == 0

        with file_lock(target, timeout=2):
            pass
    finally:
        release.set()
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


def test_processes_racing_on_first_lock_file_creation_succeed(tmp_path: Path) -> None:
    target = tmp_path / "new" / "results.json"
    context = multiprocessing.get_context("spawn")
    process_count = 3
    barrier = context.Barrier(process_count)
    acquired = context.Queue()
    processes = [
        context.Process(target=_race_first_file_lock, args=(str(target), barrier, acquired))
        for _ in range(process_count)
    ]

    for process in processes:
        process.start()

    try:
        for process in processes:
            process.join(timeout=10)
        assert all(not process.is_alive() for process in processes)
        assert [process.exitcode for process in processes] == [0] * process_count
        assert [acquired.get(timeout=2) for _ in processes] == [True] * process_count
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        acquired.close()


def test_lock_file_remains_after_release(tmp_path: Path) -> None:
    target = tmp_path / "results.json"
    lock_file = target.with_name("results.json.csat.lock")

    with file_lock(target):
        assert lock_file.exists()

    assert lock_file.exists()


def test_lock_file_name_appends_suffix_to_resolved_target(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "publish"

    with file_lock(target):
        expected = Path(f"{target.resolve()}.csat.lock")
        assert expected.exists()
        assert expected.name == "publish.csat.lock"
