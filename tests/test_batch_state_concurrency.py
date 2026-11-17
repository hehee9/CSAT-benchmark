"""@description 배치 상태의 동시 제출, 폴링 및 다운로드 병합 검증"""

from __future__ import annotations

import copy
import multiprocessing
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import csat_benchmark.batch as batch
from tests.test_batch import _FakeBatchTransport, _XaiBatchTransport, _write_config, _write_exam


def _job(name: str) -> dict:
    """@description 상태 병합 검증용 최소 공급자 작업 생성"""
    metadata = {"identity": ["국어/예시1", name, 1]}
    return {
        "model_name": name,
        "provider": "openai",
        "provider_batch_id": name,
        "input_path": f"{name}.jsonl",
        "request_ids": [name],
        "request_map": {name: metadata},
        "status": "submitted",
        "status_info": {},
        "downloaded": False,
        "merged_request_ids": [],
    }


def _append_job(state: batch._BatchState, name: str) -> dict:
    """@description 작업 및 최신 요청 맵의 동시 추가"""
    job = _job(name)
    state["jobs"].append(job)
    state["request_map"][name] = dict(job["request_map"][name], provider_batch_id=name)
    return job


def _save_worker(index: str, prefix: str, start) -> None:
    """@description 독립 프로세스의 반복적인 서로 다른 작업 저장"""
    path = Path(index)
    state = batch._load_batch_state(path, {"exam_id": "fixture", "mode": "default"})
    start.wait(20)
    for number in range(20):
        _append_job(state, f"{prefix}-{number}")
        batch._save_json(batch._state_path(path), state)


def test_spawn_processes_merge_disjoint_job_deltas(tmp_path: Path):
    """@description 오래된 상태를 가진 두 프로세스의 반복 저장 중 작업 유실 방지"""
    context = multiprocessing.get_context("spawn")
    start = context.Barrier(2)
    processes = [
        context.Process(target=_save_worker, args=(str(tmp_path / "index.json"), prefix, start))
        for prefix in ("first", "second")
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(40)
        if process.is_alive():
            process.terminate()
            process.join()
        assert process.exitcode == 0
    state = batch._load_batch_state(tmp_path / "index.json", {"exam_id": "fixture", "mode": "default"})
    expected = {f"{prefix}-{number}" for prefix in ("first", "second") for number in range(20)}
    assert {job["provider_batch_id"] for job in state["jobs"]} == expected
    assert set(state["request_map"]) == expected


def test_wait_snapshot_save_preserves_a_concurrent_submit(tmp_path: Path, monkeypatch):
    """@description 이전 교시 폴링 저장 시 다음 교시 제출과 요청 맵 보존"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, targets=2, questions=1)
    config = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    batch.submit_exam(exam, config_path=config, targets=["국어/예시1"], transport=transport)
    original_status = transport.status
    submitted = False

    def _status(batch_id, model_config):
        """@description 대기 스냅샷을 만든 뒤 다른 범위 제출"""
        nonlocal submitted
        if not submitted:
            submitted = True
            batch.submit_exam(exam, config_path=config, targets=["국어/예시2"], transport=transport)
        return original_status(batch_id, model_config)

    monkeypatch.setattr(transport, "status", _status)
    result = batch.wait_exam(
        exam, config_path=config, targets=["국어/예시1"], transport=transport, download=False, check_interval=0,
    )
    assert {job["provider_batch_id"] for job in result["batch_state"]["jobs"]} == {"fake-1", "fake-2"}
    assert {metadata["provider_batch_id"] for metadata in result["batch_state"]["request_map"].values()} == {"fake-1", "fake-2"}


def test_same_scope_submit_is_reserved_before_network(tmp_path: Path, monkeypatch):
    """@description 첫 전송 중 두 번째 같은 범위 제출 거부 및 네트워크 외부 잠금"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    entered = threading.Event()
    release = threading.Event()
    original_submit = transport.submit

    def _submit(*args, **kwargs):
        """@description 첫 공급자 전송 중 두 번째 호출 허용"""
        entered.set()
        assert release.wait(15)
        return original_submit(*args, **kwargs)

    monkeypatch.setattr(transport, "submit", _submit)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(batch.submit_exam, exam, config_path=config, transport=transport)
        try:
            assert entered.wait(15)
            with pytest.raises(batch.BatchError, match="이미 처리 중"):
                batch.submit_exam(exam, config_path=config, transport=transport)
        finally:
            release.set()
        assert first.result()["submitted"] == 1
    assert len(transport.submissions) == 1


@pytest.mark.parametrize("field", ["provider_batch_id", "request_map"])
def test_download_rechecks_job_before_result_upsert(tmp_path: Path, monkeypatch, capsys, field: str):
    """@description 다운로드 중 작업 ID 또는 요청 맵 교체 시 결과 병합 생략"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    submitted = batch.submit_exam(exam, config_path=config, transport=transport)
    index = Path(submitted["path"])
    original_parse = transport.parse

    def _parse(*args, **kwargs):
        """@description 파싱 도중 최신 작업 정보 변경"""
        state = batch._load_batch_state(index, submitted["run"])
        job = state["jobs"][0]
        if field == "provider_batch_id":
            job[field] = "replacement"
        else:
            first_id = job["request_ids"][0]
            job[field][first_id]["question_number"] = 99
        batch._save_json(batch._state_path(index), state)
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(transport, "parse", _parse)
    result = batch.download_exam(exam, config_path=config, transport=transport)
    assert result["saved_results"] == 0
    assert result["run"]["results"] == []
    assert "작업 정보가 변경" in capsys.readouterr().out


def test_two_downloaders_do_not_parse_each_others_partial_raw(tmp_path: Path, monkeypatch):
    """@description 같은 작업의 중복 다운로드 중 부분 raw 읽기 및 결과 유실 방지"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    batch.submit_exam(exam, config_path=config, transport=transport)
    downloads_started = threading.Barrier(2)
    partial_written = threading.Event()
    first_parsed = threading.Event()
    call_lock = threading.Lock()
    calls = 0
    original_download = transport.download
    original_parse = transport.parse
    paths = []

    def _download(batch_id, model_config, output_path):
        """@description 첫 응답 파싱 중 두 번째 응답의 부분 쓰기 유지"""
        nonlocal calls
        with call_lock:
            calls += 1
            call_number = calls
            paths.append(output_path)
        downloads_started.wait(15)
        if call_number == 1:
            result = original_download(batch_id, model_config, output_path)
            assert partial_written.wait(15)
            return result
        with output_path.open("w", encoding="utf-8") as output:
            output.write("[")
            output.flush()
            partial_written.set()
            assert first_parsed.wait(15)
        return original_download(batch_id, model_config, output_path)

    def _parse(*args, **kwargs):
        """@description 완전한 raw 응답 파싱 후 두 번째 다운로드 재개"""
        try:
            return original_parse(*args, **kwargs)
        finally:
            first_parsed.set()

    monkeypatch.setattr(transport, "download", _download)
    monkeypatch.setattr(transport, "parse", _parse)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(batch.download_exam, exam, config_path=config, transport=transport) for _ in range(2)]
        results = [future.result(timeout=25) for future in futures]
    assert len(set(paths)) == 2
    assert all(result["batch_state"]["jobs"][0]["downloaded"] for result in results)
    final = batch.RunStore.load(results[0]["path"])
    assert len(final.run["results"]) == 1
    assert final.run["results"][0]["raw_response"] == "응답 fake-1"
    assert not any(path.exists() for path in paths)


def test_state_status_and_download_progress_never_regress(tmp_path: Path):
    """@description 오래된 폴링 결과의 종료 상태, 다운로드 및 요청 병합 역행 방지"""
    index = tmp_path / "index.json"
    run = {"exam_id": "fixture", "mode": "default"}
    initial = batch._load_batch_state(index, run)
    _append_job(initial, "job")
    batch._save_json(batch._state_path(index), initial)
    older = batch._load_batch_state(index, run)
    newer = batch._load_batch_state(index, run)
    batch._update_job_status(newer["jobs"][0], {"status": "completed"}, 200)
    newer["jobs"][0].update(downloaded=True, merged_request_ids=["job"])
    batch._save_json(batch._state_path(index), newer)
    batch._update_job_status(older["jobs"][0], {"status": "in_progress"}, 300)
    batch._save_json(batch._state_path(index), older)
    assert older["jobs"][0]["status"] == "completed"
    assert older["jobs"][0]["downloaded"] is True
    assert older["jobs"][0]["merged_request_ids"] == ["job"]


def test_same_status_stage_prefers_newer_observation(tmp_path: Path):
    """@description 동일 상태 단계의 늦게 저장된 이전 관측값 무시"""
    index = tmp_path / "index.json"
    run = {"exam_id": "fixture", "mode": "default"}
    state = batch._load_batch_state(index, run)
    _append_job(state, "job")
    batch._save_json(batch._state_path(index), state)
    older = copy.deepcopy(state)
    batch._update_job_status(state["jobs"][0], {"status": "in_progress", "completed": 3}, 200)
    batch._save_json(batch._state_path(index), state)
    batch._update_job_status(older["jobs"][0], {"status": "in_progress", "completed": 1}, 100)
    batch._save_json(batch._state_path(index), older)
    assert older["jobs"][0]["status_info"]["completed"] == 3


def test_submit_failure_releases_reservation_for_retry(tmp_path: Path, monkeypatch):
    """@description 공급자 제출 실패 후 기존 재시도 흐름을 위한 예약 해제"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    original_submit = transport.submit

    def _submit(*args, **kwargs):
        """@description 공급자 응답 실패 대역"""
        raise TimeoutError("전송 실패")

    monkeypatch.setattr(transport, "submit", _submit)
    with pytest.raises(TimeoutError, match="전송 실패"):
        batch.submit_exam(exam, config_path=config, transport=transport)
    monkeypatch.setattr(transport, "submit", original_submit)
    result = batch.submit_exam(exam, config_path=config, transport=transport)
    assert result["submitted"] == 1
    assert len(transport.submissions) == 1


def test_dead_process_reservation_does_not_block_submit(tmp_path: Path, monkeypatch):
    """@description 종료된 프로세스의 미완료 예약이 다음 제출을 막지 않음"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    submitted = batch.submit_exam(exam, config_path=config, transport=transport)
    index = Path(submitted["path"])
    state = batch._load_batch_state(index, submitted["run"])
    state["jobs"][0].update(provider_batch_id="reserved:dead", owner_pid=99999999, reserved_at=time.time())
    batch._save_json(batch._state_path(index), state)
    assert batch._pid_is_alive(99999999) is False
    result = batch.submit_exam(exam, config_path=config, transport=transport)
    assert result["submitted"] == 1
    assert len(transport.submissions) == 2


def test_live_process_reservation_is_not_expired_by_age():
    """@description 살아 있는 프로세스의 장시간 업로드 예약 유지"""
    job = _job("reserved")
    job.update(provider_batch_id="reserved:live", owner_pid=os.getpid(), reserved_at=time.time() - 7200)
    assert batch._job_is_active(job)


def test_xai_downloader_between_chunks_waits_for_complete_submission(tmp_path: Path, monkeypatch, capsys):
    """@description xAI 청크 전송 중 조회 생략 및 제출 완료 후 전체 결과 회수"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=2)
    config = _write_config(tmp_path, ["모의 모델"], api_type="grok")
    transport = _XaiBatchTransport()
    original_add = transport.add
    snapshots = []

    def _add(*args, before_chunk=None, after_chunk=None, **kwargs):
        """@description 첫 청크 승인 후 다른 스레드에서 조회와 다운로드 실행"""
        def _after_chunk(chunk, number, total):
            """@description 부분 제출 상태 저장 직후 병행 터미널 동작 재현"""
            after_chunk(chunk, number, total)
            if number == 1:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    snapshots.append(executor.submit(
                        batch.download_exam, exam, config_path=config, easy=True, transport=transport,
                    ).result(timeout=15))
                assert batch.status_exam(exam, config_path=config, easy=True, transport=transport)["statuses"] == []
                assert batch.wait_exam(
                    exam, config_path=config, easy=True, transport=transport, download=False, check_interval=0,
                )["statuses"] == []

        return original_add(*args, before_chunk=before_chunk, after_chunk=_after_chunk, **kwargs)

    monkeypatch.setattr(transport, "add", _add)
    batch.submit_exam(exam, config_path=config, easy=True, transport=transport)
    assert snapshots[0]["saved_results"] == 0
    assert snapshots[0]["downloaded"] == 0
    assert transport.status_calls == []
    assert capsys.readouterr().out.splitlines() == [
        "다른 프로세스에서 제출 중인 배치 작업 1개를 건너뜁니다."
    ] * 3
    result = batch.download_exam(exam, config_path=config, easy=True, transport=transport)
    assert result["saved_results"] == 2
    assert len(result["run"]["results"]) == 2
    assert result["batch_state"]["jobs"][0]["downloaded"] is True


def test_xai_incomplete_raw_is_not_reused_after_submission_completes(tmp_path: Path, monkeypatch):
    """@description 중단된 xAI 제출의 부분 raw를 완료된 제출의 전체 raw로 재사용 방지"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=2)
    config = _write_config(tmp_path, ["모의 모델"], api_type="grok")
    transport = _XaiBatchTransport(failed_chunk=2)
    with pytest.raises(RuntimeError, match="청크 추가 실패"):
        batch.submit_exam(exam, config_path=config, easy=True, transport=transport)
    partial = batch.download_exam(exam, config_path=config, easy=True, transport=transport)
    assert partial["saved_results"] == 1
    partial_path = partial["batch_state"]["jobs"][0]["raw_path"]
    index = Path(partial["path"])
    state = batch._load_batch_state(index, partial["run"])
    job = state["jobs"][0]
    transport.batches[job["provider_batch_id"]] = list(job["request_ids"])
    job.update(submission_status="complete", submitted_request_ids=list(job["request_ids"]))
    batch._save_json(batch._state_path(index), state)
    final = batch.download_exam(exam, config_path=config, easy=True, transport=transport)
    assert final["saved_results"] == 1
    assert len(final["run"]["results"]) == 2
    assert final["batch_state"]["jobs"][0]["downloaded"] is True
    assert final["batch_state"]["jobs"][0]["raw_path"] != partial_path


def test_xai_dead_submitter_can_recover_accepted_results(tmp_path: Path, monkeypatch):
    """@description 종료된 xAI 제출 프로세스가 승인받은 청크 결과 회수 유지"""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=2)
    config = _write_config(tmp_path, ["모의 모델"], api_type="grok")
    transport = _XaiBatchTransport(failed_chunk=2)
    index = tmp_path / "run" / "results.json"
    with pytest.raises(RuntimeError, match="청크 추가 실패"):
        batch.submit_exam(exam, config_path=config, easy=True, output=index, transport=transport)
    run = batch.RunStore.load(index)
    state = batch._load_batch_state(run.path, run.run)
    state["jobs"][0].update(submission_status="in_progress", owner_pid=99999999)
    batch._save_json(batch._state_path(run.path), state)
    result = batch.download_exam(exam, config_path=config, easy=True, output=index, transport=transport)
    assert result["saved_results"] == 1


def test_skipped_submissions_notice_counts_live_jobs_once(capsys):
    """@description 활성 예약과 청크 제출 건수 안내를 명령당 한 번만 출력"""
    state = batch._BatchState(batch._new_batch_state({"exam_id": "fixture", "mode": "default"}))
    for name in ("reserved:live", "chunked", "reserved:released"):
        job = _append_job(state, name)
        for metadata in job["request_map"].values():
            metadata.update(target="국어/예시1", question_number=1)
        job.update(
            provider="grok", owner_pid=os.getpid(), reserved_at=time.time(), submission_status="in_progress",
        )
        if name.endswith("released"):
            job["reservation_released"] = True
    context = {
        "state": state,
        "selected_models": set(),
        "selected_targets": {"국어/예시1"},
        "question_numbers": None,
    }
    assert batch._selected_operation_jobs(context) == []
    assert batch._selected_operation_jobs(context) == []
    assert capsys.readouterr().out == "다른 프로세스에서 제출 중인 배치 작업 2개를 건너뜁니다.\n"
