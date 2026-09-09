"""채점 모드별 병렬 처리와 진행 출력 집중 검증."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

from csat_benchmark.evaluation import grade_run
from csat_benchmark.exams import load_exam
from csat_benchmark.runs import create_run


def _make_exam(
    tmp_path: Path,
    sections: list[tuple[str, str, str]],
    *,
    mode: str,
    input_mode: str,
):
    """@description 병렬 채점 테스트용 다중 섹션 시험 생성"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    manifest_sections = []
    for index, (target, subject, section) in enumerate(sections, 1):
        question_file = f"questions_{index}.json"
        text_file = f"question_{index}.txt"
        (data_dir / question_file).write_text(
            json.dumps(
                {
                    "subject": subject,
                    "section": section,
                    "questions": [
                        {
                            "number": 1,
                            "correct_answer": 1,
                            "points": 2,
                            "question_path": text_file,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (data_dir / text_file).write_text(f"{target} 본문", encoding="utf-8")
        manifest_sections.append(
            {
                "target": target,
                "subject": subject,
                "section": section,
                "group": subject,
                "kind": "common",
                "questions": question_file,
                "max_points": 2,
            }
        )

    manifest_path = tmp_path / "exam.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "concurrency-test",
                "title": "병렬 채점 시험",
                "data_dir": "data",
                "results_dir": "results",
                "sections": manifest_sections,
                "modes": [{"id": mode, "label": mode, "input_mode": input_mode}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return load_exam(manifest_path, project_root=tmp_path)


def _make_run(exam, sections: list[tuple[str, str, str]], models: list[str], *, mode: str, input_mode: str):
    """@description 병렬 채점 테스트용 정본 실행 생성"""
    run = create_run(
        exam_id=exam.id,
        mode=mode,
        input_mode=input_mode,
        selected_targets=[target for target, _, _ in sections],
        selected_models=[{"name": model, "model_id": model} for model in models],
        input_context=[
            {"target": target, "question_numbers": [1]} for target, _, _ in sections
        ],
    )
    for target, subject, section in sections:
        for model in models:
            run["results"].append(
                {
                    "target": target,
                    "subject": subject,
                    "section": section,
                    "model_name": model,
                    "question_number": 0 if input_mode == "section" else 1,
                    "success": True,
                    "raw_response": "1",
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "total_tokens": 3,
                    "answer_status": None,
                    "provider_stop_reason": None,
                }
            )
    return run


class _HardConcurrencyVerifier:
    """@description 기본 모드 모델 작업의 동시 진입을 확인하는 검증기 대역"""

    def __init__(self, parties: int):
        self.barrier = threading.Barrier(parties)
        self.lock = threading.Lock()
        self.first_calls = 0
        self.active = 0
        self.max_active = 0
        self.models: list[str] = []

    def verify_hard_answers(self, raw_response, question_infos):
        del question_infos
        model_name = raw_response
        with self.lock:
            self.models.append(model_name)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.first_calls += 1
            is_first_batch = self.first_calls <= self.barrier.parties
        if is_first_batch:
            self.barrier.wait(timeout=5)
        time.sleep(0.005)
        with self.lock:
            self.active -= 1
        return [{"question_number": 1, "correct_answer": 1, "llm_answer": int(raw_response)}]


def test_default_mode_runs_sections_and_models_concurrently(tmp_path: Path):
    """@description 기본 모드의 전체 섹션·섹션별 모델 동시 채점 확인"""
    sections = [("국어/1", "국어", "1"), ("수학/1", "수학", "1")]
    exam = _make_exam(tmp_path, sections, mode="default", input_mode="section")
    run = _make_run(exam, sections, ["모델A", "모델B"], mode="default", input_mode="section")
    verifier = _HardConcurrencyVerifier(parties=4)

    graded = grade_run(run, exam, verifier)

    assert verifier.max_active >= 4
    assert len(graded["results"]) == 4
    assert graded["score_by_model"] == {"모델A": 4, "모델B": 4}


class _QuestionConcurrencyVerifier:
    """@description 쉬움 모드 과목·문항 작업 순서를 확인하는 검증기 대역"""

    def __init__(self, first_batch: int):
        self.barrier = threading.Barrier(first_batch)
        self.lock = threading.Lock()
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self.first_calls = 0

    def verify_answer(self, raw_response, correct_answer, question_number, question_text):
        del raw_response, correct_answer, question_number
        target = question_text.split(" 본문", 1)[0]
        with self.lock:
            self.calls.append(target)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.first_calls += 1
            is_first_batch = self.first_calls <= self.barrier.parties
        if is_first_batch:
            self.barrier.wait(timeout=5)
        time.sleep(0.005)
        with self.lock:
            self.active -= 1
        return 1


def test_easy_mode_keeps_subjects_sequential_and_inner_work_concurrent(tmp_path: Path):
    """@description 쉬움 모드의 과목 순차·내부 작업 병렬 처리 확인"""
    sections = [("국어/1", "국어", "1"), ("국어/2", "국어", "2"), ("수학/1", "수학", "1")]
    exam = _make_exam(tmp_path, sections, mode="easy", input_mode="question")
    run = _make_run(exam, sections, ["모델A", "모델B"], mode="easy", input_mode="question")
    verifier = _QuestionConcurrencyVerifier(first_batch=4)

    graded = grade_run(run, exam, verifier)

    assert verifier.max_active >= 4
    assert set(verifier.calls[:8]) == {"국어/1", "국어/2"}
    assert verifier.calls[8] == "수학/1"
    assert len(graded["results"]) == 6
    assert graded["complete_by_model"] == {"모델A": True, "모델B": True}


class _ManualReviewVerifier:
    """@description 진행 출력과 수동 검토 표시를 확인하는 검증기 대역"""

    def __init__(self):
        self.calls = 0

    def verify_answer(self, raw_response, correct_answer, question_number, question_text):
        del raw_response, correct_answer, question_number, question_text
        self.calls += 1
        return [1, 2, 3][self.calls - 1]


class _ReverseHardVerifier:
    """@description 완료 순서와 무관한 hard 채점 집계를 확인하는 검증기 대역"""

    def __init__(self):
        self.calls = 0
        self.models: list[str] = []

    def verify_hard_answers(self, raw_response, question_infos):
        answer, delay, model_name = raw_response.split("|")
        self.calls += 1
        self.models.append(model_name)
        time.sleep(float(delay))
        return [
            {
                "question_number": info["number"],
                "correct_answer": info["correct_answer"],
                "llm_answer": int(answer),
            }
            for info in question_infos
        ]


def test_reversed_completion_keeps_sorted_answers_scores_and_tokens(tmp_path: Path):
    """@description 완료 순서 역전 시 답안·점수·토큰 필드 보존 확인"""
    sections = [("국어/1", "국어", "1"), ("수학/1", "수학", "1")]
    models = ["모델A", "모델B"]
    exam = _make_exam(tmp_path, sections, mode="default", input_mode="section")
    run = _make_run(exam, sections, models, mode="default", input_mode="section")
    for result in run["results"]:
        if result["model_name"] == "모델A":
            result["raw_response"] = "1|0.03|모델A"
            result["input_tokens"] = 11
            result["output_tokens"] = 1
            result["total_tokens"] = 12
        else:
            result["raw_response"] = "2|0|모델B"
            result["input_tokens"] = 13
            result["output_tokens"] = 2
            result["total_tokens"] = 15
    verifier = _ReverseHardVerifier()

    graded = grade_run(run, exam, verifier)

    keys = [(row["target"], row["model_name"], row["question_number"]) for row in graded["results"]]
    assert keys == sorted(keys)
    assert graded["score_by_model"] == {"모델A": 4, "모델B": 0}
    assert {
        row["model_name"]: (row["input_tokens"], row["output_tokens"], row["total_tokens"])
        for row in graded["results"]
    } == {"모델A": (11, 1, 12), "모델B": (13, 2, 15)}


def test_model_filter_grades_only_selected_model(tmp_path: Path):
    """@description 모델 필터 지정 시 선택 모델만 채점·저장 대상 유지 확인"""
    sections = [("국어/1", "국어", "1"), ("수학/1", "수학", "1")]
    models = ["모델A", "모델B"]
    exam = _make_exam(tmp_path, sections, mode="default", input_mode="section")
    run = _make_run(exam, sections, models, mode="default", input_mode="section")
    for result in run["results"]:
        result["raw_response"] = f"1|0|{result['model_name']}"
    verifier = _ReverseHardVerifier()

    graded = grade_run(run, exam, verifier, model_names=["모델B"])

    assert graded["selected_models"] == ["모델B"]
    assert {row["model_name"] for row in graded["results"]} == {"모델B"}
    assert graded["score_by_model"] == {"모델B": 4}
    assert verifier.calls == 4


def test_explicit_model_with_mixed_target_history_grades_only_ungraded_target(tmp_path: Path):
    """@description 선택 모델의 완료 target과 미완료 target을 분리 채점"""
    sections = [("국어/1", "국어", "1"), ("수학/1", "수학", "1")]
    exam = _make_exam(tmp_path, sections, mode="default", input_mode="section")
    run = _make_run(exam, sections, ["모델"], mode="default", input_mode="section")
    for result in run["results"]:
        result["raw_response"] = f"1|0|{result['target']}"
    prior = {
        "selected_models": ["모델"],
        "results": [
            {
                "target": "국어/1",
                "subject": "국어",
                "section": "1",
                "model_name": "모델",
                "question_number": 1,
                "extracted_answer": 1,
                "correct_answer": 1,
                "is_correct": True,
                "points": 2,
                "answer_status": "answered",
                "complete": True,
                "provenance": "graded",
            }
        ],
    }
    verifier = _ReverseHardVerifier()

    graded = grade_run(run, exam, verifier, model_names=["모델"], verified=prior)

    assert verifier.models == ["수학/1", "수학/1"]
    assert {row["target"] for row in graded["results"]} == {"국어/1", "수학/1"}


def test_progress_is_printed_before_grade_run_returns_and_marks_manual_review(
    tmp_path: Path, capsys
):
    """@description 문항 완료 출력의 선행과 정오답·수동 검토 표시 확인"""
    sections = [("국어/1", "국어", "1")]
    exam = _make_exam(tmp_path, sections, mode="easy", input_mode="question")
    run = _make_run(exam, sections, ["모델"], mode="easy", input_mode="question")
    verifier = _ManualReviewVerifier()
    progress_seen = threading.Event()
    release_return = threading.Event()
    result_holder: list[dict] = []
    errors: list[BaseException] = []

    import builtins

    original_print = builtins.print

    def _print_spy(*args, **kwargs):
        """@description 진행 출력 관찰 및 반환 전 대기"""
        original_print(*args, **kwargs)
        text = " ".join(str(arg) for arg in args)
        if "문제 1번" in text and "✓" in text:
            progress_seen.set()
            release_return.wait(timeout=5)

    def _run():
        """@description 백그라운드 채점 실행"""
        try:
            result_holder.append(grade_run(run, exam, verifier))
        except BaseException as error:
            errors.append(error)

    with patch("builtins.print", _print_spy):
        thread = threading.Thread(target=_run)
        thread.start()
        assert progress_seen.wait(timeout=5)
        assert thread.is_alive()
        before_return = capsys.readouterr().out
        release_return.set()
        thread.join(timeout=5)
    after_return = capsys.readouterr().out

    assert not errors
    assert not thread.is_alive()
    assert result_holder[0]["results"][0]["needs_manual_review"] is True
    output = before_return + after_return
    assert "[1/1] ✓ 모델 - 문제 1번" in output
    assert "[수동검토필요]" in output
    assert "수동 검토 필요 항목 (1개)" in output
