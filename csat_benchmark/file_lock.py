"""@description 파일 잠금의 프로세스 간 동기화와 전역 획득 순서 정의

모든 호출자는 batch state -> publish (exam/mode) -> run index -> per-model
verified -> web model metadata 순서로 잠금을 획득해야 합니다. 역순으로 획득하면 안 됩니다.
"""

from __future__ import annotations

import errno
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class FileLockTimeout(TimeoutError):
    """@description 제한 시간 내에 파일 잠금을 획득하지 못한 경우"""


_REGISTRY_LOCK = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCK_COUNTS = threading.local()
_RETRY_INTERVAL_SECONDS = 0.05


def _path_thread_lock(lock_key: str) -> threading.RLock:
    """@description 경로별 프로세스 내 재진입 잠금 반환"""
    with _REGISTRY_LOCK:
        lock = _PATH_LOCKS.get(lock_key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[lock_key] = lock
        return lock


def _try_lock_file(file_descriptor: int, lock_path: Path, deadline: float, timeout: float) -> None:
    """@description 잠금 파일의 첫 바이트를 제한 시간 동안 잠금"""
    first_attempt = True
    while first_attempt or time.monotonic() < deadline:
        first_attempt = False
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FileLockTimeout(
                    f"잠금 파일 {lock_path}을(를) {timeout}초 안에 획득하지 못했습니다."
                ) from error
            time.sleep(min(_RETRY_INTERVAL_SECONDS, remaining))
    raise FileLockTimeout(
        f"잠금 파일 {lock_path}을(를) {timeout}초 안에 획득하지 못했습니다."
    )


def _unlock_file(file_descriptor: int) -> None:
    """@description 운영체제 파일 잠금 해제"""
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(file_descriptor, fcntl.LOCK_UN)


@contextmanager
def file_lock(path: str | Path, timeout: float = 120.0) -> Iterator[None]:
    """@description path를 대상으로 배타적 프로세스 간 잠금 제공"""
    target_path = Path(path).resolve()
    lock_path = Path(f"{target_path}.csat.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = os.path.normcase(os.path.abspath(lock_path))
    thread_lock = _path_thread_lock(lock_key)
    timeout = float(timeout)
    deadline = time.monotonic() + max(timeout, 0.0)

    if not thread_lock.acquire(timeout=max(deadline - time.monotonic(), 0.0)):
        raise FileLockTimeout(
            f"잠금 파일 {lock_path}을(를) {timeout}초 안에 획득하지 못했습니다."
        )

    thread_counts = getattr(_THREAD_LOCK_COUNTS, "counts", None)
    if thread_counts is None:
        thread_counts = {}
        _THREAD_LOCK_COUNTS.counts = thread_counts

    is_outermost = thread_counts.get(lock_key, 0) == 0
    file_descriptor = None
    os_lock_acquired = False
    try:
        if is_outermost:
            open_flags = os.O_CREAT | os.O_RDWR
            if os.name == "nt":
                open_flags |= os.O_BINARY
            file_descriptor = os.open(lock_path, open_flags, 0o666)
            _try_lock_file(file_descriptor, lock_path, deadline, timeout)
            os_lock_acquired = True
        thread_counts[lock_key] = thread_counts.get(lock_key, 0) + 1
        try:
            yield
        finally:
            remaining_count = thread_counts[lock_key] - 1
            if remaining_count:
                thread_counts[lock_key] = remaining_count
            else:
                del thread_counts[lock_key]
                if os_lock_acquired:
                    try:
                        _unlock_file(file_descriptor)
                    finally:
                        os.close(file_descriptor)
                        file_descriptor = None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        thread_lock.release()
