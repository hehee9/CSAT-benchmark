"""@description 다중 프로세스 정본 병합과 채점 무효화 경쟁 검증"""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from csat_benchmark.evaluation import save_verified
from csat_benchmark.runs import (
    create_run, initialize_model_results, invalidate_verified_results, load_run,
    merge_run, model_results_path, model_verified_path, save_run, save_run_metadata,
    upsert_result, utc_now,
)


def _run(model: str, target: str):
    """@description 독립 모델·영역 실행 생성"""
    return create_run(
        exam_id="concurrency", mode="default", input_mode="question",
        selected_models=[{"name": model, "model_id": model}], selected_targets=[target],
        input_context=[{
            "target": target, "question_numbers": [1],
            "questions": [{"number": 1, "text": target}], "prepared_question": target,
        }], system_prompt=model,
    )


def _raw(model: str, target: str, number: int = 1, response: str = "old") -> dict:
    """@description 정본 저장 계약의 모의 원본 응답 생성"""
    return {
        "model_name": model, "target": target, "subject": target, "section": "예시",
        "question_number": number, "raw_response": response, "success": True,
        "timestamp": utc_now(),
    }


def _worker(index: str, model: str, barrier) -> None:
    """@description 독립 프로세스에서 동시 시작 후 50개 결과 저장"""
    run = _run(model, model)
    barrier.wait(timeout=30)
    merge_run(run, index)
    for number in range(1, 51):
        upsert_result(run, _raw(model, model, number), path=index)


def _grading(index: Path, raw: dict, *, reused: bool = False) -> dict:
    """@description 이번 채점과 재사용 행을 구분한 저장 입력 생성"""
    row = {
        **raw, "complete": True, "correct_answer": 1, "extracted_answer": 1,
        "is_correct": True, "points": 2, "provenance": "graded",
    }
    key = [raw["target"], raw["model_name"], raw["question_number"]]
    return {
        "schema_version": 1, "exam_id": "concurrency", "mode": "default",
        "selected_models": [raw["model_name"]], "results": [row],
        "grading_started_at": utc_now(), "graded_keys": [] if reused else [key],
        "raw_index_path": str(index),
    }


def _rows(index: Path, model: str) -> list:
    """@description 모델별 저장 검증 행 로드"""
    return json.loads(model_verified_path(index, model).read_text(encoding="utf-8"))["results"]


def test_stale_runs_preserve_other_models_targets_contexts_and_snapshots(tmp_path):
    """@description 오래된 두 호출자의 결과·메타데이터 교차 저장 무손실 확인"""
    index = tmp_path / "results.json"
    first, second = _run("A", "국어"), _run("B", "수학")
    created_at = first["created_at"]
    merge_run(first, index)
    merge_run(second, index)
    upsert_result(first, _raw("A", "국어"), path=index)
    first_alias = first
    second["selected_models"][1]["model_id"] = "new-B"
    second["input_context"][1]["prepared_question"] = "new-math"
    save_run_metadata(second, index)
    save_run_metadata(first, index)
    upsert_result(second, _raw("B", "수학"), path=index)
    save_run_metadata(first, index)
    loaded = load_run(index)
    assert first_alias is first
    assert first["results"] == loaded["results"]
    assert loaded["created_at"] == created_at
    assert loaded["system_prompt"] == "B"
    assert loaded["selected_targets"] == ["국어", "수학"]
    assert [model["name"] for model in loaded["selected_models"]] == ["A", "B"]
    assert loaded["selected_models"][1]["model_id"] == "new-B"
    assert loaded["input_context"][1]["prepared_question"] == "new-math"
    assert {row["model_name"] for row in loaded["results"]} == {"A", "B"}


def test_stale_upserts_for_same_model_preserve_all_result_keys(tmp_path):
    """@description 동일 모델의 오래된 원본 목록에서 단일 key만 갱신"""
    index = tmp_path / "results.json"
    first, second = _run("A", "국어"), _run("A", "국어")
    merge_run(first, index)
    merge_run(second, index)
    upsert_result(first, _raw("A", "국어", 1), path=index)
    upsert_result(second, _raw("A", "국어", 2), path=index)
    upsert_result(first, _raw("A", "국어", 1, "new"), path=index)
    assert [(row["question_number"], row["raw_response"]) for row in load_run(index)["results"]] == [
        (1, "new"), (2, "old"),
    ]


def test_spawned_writers_merge_disjoint_startup_and_100_results(tmp_path):
    """@description 두 spawn 프로세스의 동시 생성·100개 저장에서 손실 방지"""
    index = tmp_path / "results.json"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes = [context.Process(target=_worker, args=(str(index), model, barrier)) for model in ("A", "B")]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=60)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()
    loaded = load_run(index)
    assert {model["name"] for model in loaded["selected_models"]} == {"A", "B"}
    assert set(loaded["selected_targets"]) == {"A", "B"}
    assert {context["target"] for context in loaded["input_context"]} == {"A", "B"}
    assert len(loaded["results"]) == 100
    for model in ("A", "B"):
        assert {row["question_number"] for row in loaded["results"] if row["model_name"] == model} == set(range(1, 51))


def test_invalidation_during_grading_blocks_old_rows_and_keeps_other_targets(tmp_path, capsys):
    """@description 채점 중 무효화된 영역만 차단하고 다른 영역 보존"""
    index = tmp_path / "results.json"
    run = _run("A", "국어")
    merge_run(run, index)
    raw = _raw("A", "국어")
    upsert_result(run, raw, path=index)
    save_verified(_grading(index, raw), index)
    math = _run("A", "수학")
    merge_run(math, index)
    math_raw = _raw("A", "수학")
    upsert_result(math, math_raw, path=index)
    save_verified(_grading(index, math_raw), index)
    grading = _grading(index, raw)
    invalidate_verified_results(index, "A", "국어", 1, input_mode="question")
    save_verified(grading, index)
    assert [row["target"] for row in _rows(index, "A")] == ["수학"]
    assert "1개 저장 건너뜀 (채점 시작 후 원본 무효화)" in capsys.readouterr().out
    envelope = json.loads(model_verified_path(index, "A").read_text(encoding="utf-8"))
    assert "1" in envelope["question_invalidations"]["국어"]


def test_reused_prior_rows_do_not_resurrect_after_invalidation(tmp_path):
    """@description 재사용한 이전 검증 행은 저장 병합에서 제외"""
    index = tmp_path / "results.json"
    run = _run("A", "국어")
    merge_run(run, index)
    raw = _raw("A", "국어")
    upsert_result(run, raw, path=index)
    save_verified(_grading(index, raw), index)
    reused = _grading(index, raw, reused=True)
    invalidate_verified_results(index, "A", "국어", 1, input_mode="question")
    save_verified(reused, index)
    assert _rows(index, "A") == []


def test_new_raw_closes_generation_gap_and_blocks_old_grading(tmp_path):
    """@description 생성 대기 중 채점한 구원본 행을 새 원본 저장 시 제거"""
    index = tmp_path / "results.json"
    run = _run("A", "국어")
    merge_run(run, index)
    raw = _raw("A", "국어")
    upsert_result(run, raw, path=index)
    invalidate_verified_results(index, "A", "국어", 1, input_mode="question")
    gap_grading = _grading(index, raw)
    save_verified(gap_grading, index)
    assert len(_rows(index, "A")) == 1
    upsert_result(run, _raw("A", "국어", response="new"), path=index)
    assert _rows(index, "A") == []
    save_verified(gap_grading, index)
    assert _rows(index, "A") == []


def test_raw_comparison_rejects_stale_source_despite_earlier_invalidation(tmp_path, capsys):
    """@description 무효화 기록과 별개로 저장 직전 원본 대조 확인"""
    index = tmp_path / "results.json"
    run = _run("A", "국어")
    merge_run(run, index)
    old = _raw("A", "국어")
    upsert_result(run, _raw("A", "국어", response="new"), path=index)
    save_verified(_grading(index, old), index)
    assert _rows(index, "A") == []
    assert "원본 응답과 채점 원본 불일치" in capsys.readouterr().out


def test_first_verification_cannot_save_after_same_text_regeneration(tmp_path):
    """@description 첫 검증 저장 전 동일한 응답이 재생성되어도 시각으로 무효화"""
    index = tmp_path / "results.json"
    run = _run("A", "국어")
    raw = _raw("A", "국어")
    run["results"].append(raw)
    save_run(run, index)
    assert not model_verified_path(index, "A").exists()
    grading = _grading(index, raw)
    upsert_result(run, _raw("A", "국어"), path=index)
    save_verified(grading, index)
    assert _rows(index, "A") == []


def test_question_update_and_invalidation_preserve_another_question_grading(tmp_path):
    """@description 같은 영역의 다른 문항 무효화·생성이 진행 중 채점에 영향 없음 확인"""
    index = tmp_path / "results.json"
    run = _run("A", "국어")
    merge_run(run, index)
    first_raw = _raw("A", "국어", 1)
    upsert_result(run, first_raw, path=index)
    first_grading = _grading(index, first_raw)
    invalidate_verified_results(index, "A", "국어", 2, input_mode="question")
    upsert_result(run, _raw("A", "국어", 2), path=index)
    save_verified(first_grading, index)
    assert [row["question_number"] for row in _rows(index, "A")] == [1]
    envelope = json.loads(model_verified_path(index, "A").read_text(encoding="utf-8"))
    assert set(envelope["question_invalidations"]["국어"]) == {"1", "2"}
    assert "국어" not in envelope["invalidations"]


def test_verified_only_model_is_not_replaced_with_empty_raw(tmp_path):
    """@description verified 전용 모델 초기화 시 원본 부재 유지"""
    index = tmp_path / "results.json"
    run = _run("A", "국어")
    merge_run(run, index)
    raw_path = model_results_path(index, "A")
    save_verified({
        "exam_id": "concurrency", "mode": "default", "selected_models": ["A"],
        "results": [{"model_name": "A", "target": "국어", "question_number": 1, "complete": True}],
    }, index)
    raw_path.unlink()
    initialize_model_results(run, index, ["A"])
    assert not raw_path.exists()
    assert load_run(index)["results"] == []
