"""단일 생성 채점 정책과 canonical verified 결과 계약 집중 검증."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import verify_answers
from csat_benchmark import evaluation
from csat_benchmark.evaluation import grade_run, load_verified, save_verified
from csat_benchmark.grading.single import verify_hard_single_result, verify_single_result
from csat_benchmark.exams import load_exam
from csat_benchmark.runs import create_run, model_verified_path, save_run


@dataclass
class _SingleVerifier:
    answers: list[object]
    calls: int = 0

    def verify_answer(self, raw_response, correct_answer, question_number, question_text):
        self.calls += 1
        return self.answers.pop(0)


@dataclass
class _HardVerifier:
    outputs: list[object]
    calls: list[list[int]] | None = None

    def __post_init__(self):
        self.calls = []

    def verify_hard_answers(self, raw_response, question_infos):
        self.calls.append([info["number"] for info in question_infos])
        return self.outputs.pop(0)


def _info(number: int = 1, correct: int = 1) -> dict:
    return {"number": number, "correct_answer": correct, "points": 2, "question_text": "본문"}


def _answer(number: int, answer: int, correct: int = 1) -> dict:
    return {"question_number": number, "correct_answer": correct, "llm_answer": answer}


def _result(**updates) -> dict:
    result = {
        "target": "국어/예시",
        "subject": "국어",
        "section": "예시",
        "model_name": "모델",
        "question_number": 1,
        "success": True,
        "raw_response": "응답",
        "answer_status": None,
        "provider_stop_reason": None,
    }
    result.update(updates)
    return result


def test_single_uses_two_matching_checks_and_canonical_fields():
    verifier = _SingleVerifier([1, 1])
    result, manual = verify_single_result(verifier, _result(), _info(), 1, Path.cwd())
    assert verifier.calls == 2
    assert manual is None
    assert result.extracted_answer == 1
    assert result.answer_status == "answered"


def test_single_uses_conditional_third_check_and_old_manual_review():
    verifier = _SingleVerifier([1, 2, None])
    result, manual = verify_single_result(verifier, _result(), _info(), 1, Path.cwd())
    assert verifier.calls == 3
    assert result.extracted_answer == 1
    assert result.needs_manual_review is True
    assert manual == ("모델", 1, [1, 2, None])


def test_hard_missing_question_triggers_third_only_for_disputed_question():
    verifier = _HardVerifier(
        [
            [_answer(1, 1), _answer(2, 2, 2)],
            [_answer(1, 1), _answer(2, 3, 2)],
            [_answer(2, 2, 2)],
        ]
    )
    results, manual = verify_hard_single_result(
        verifier,
        _result(question_number=0),
        [_info(1, 1), _info(2, 2)],
        1,
    )
    assert verifier.calls == [[1, 2], [1, 2], [2]]
    assert {item.question_number: item.extracted_answer for item in results} == {1: 1, 2: 2}
    assert manual == []


def test_hard_refusal_and_empty_map_follow_legacy_statuses():
    refusal = _HardVerifier([])
    results, manual = verify_hard_single_result(
        refusal,
        _result(answer_status="refusal", provider_stop_reason="refusal", question_number=0),
        [_info(1)],
        1,
    )
    assert refusal.calls == []
    assert manual == []
    assert results[0].extracted_answer == -2
    assert results[0].answer_status == "refusal"

    empty = _HardVerifier([[], [], []])
    results, manual = verify_hard_single_result(
        empty,
        _result(question_number=0),
        [_info(1)],
        1,
    )
    assert empty.calls == [[1], [1], [1]]
    assert results[0].extracted_answer == -1
    assert results[0].answer_status == "no_answer"
    assert manual == []


def test_grade_run_does_not_grade_technical_incomplete_or_call_verifier(tmp_path: Path):
    exam = load_exam("example-text")
    run = create_run(
        exam_id=exam.id,
        mode="default",
        input_mode="section",
        selected_targets=["국어/예시"],
        selected_models=[{"name": "모델", "model_id": "mock"}],
        input_context=[{"target": "국어/예시", "question_numbers": [1]}],
    )
    run["results"] = [_result(question_number=0, success=False, raw_response="", answer_status="technical_failure")]

    verifier = _SingleVerifier([1, 1])
    graded = grade_run(run, exam, verifier)
    assert verifier.calls == 0
    assert graded["results"][0]["complete"] is False
    assert graded["results"][0]["is_correct"] is None
    assert "attempts" not in graded["results"][0]
    assert "aggregate" not in graded["results"][0]


def test_save_load_verified_merges_unselected_rows(tmp_path: Path):
    index = tmp_path / "results.json"
    index.write_text(
        json.dumps(
            {
                "exam_id": "example-text",
                "mode": "default",
                "selected_models": [{"name": "모델"}, {"name": "다른 모델"}],
                "selected_targets": ["국어/예시"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    existing = {
        "schema_version": 1,
        "exam_id": "example-text",
        "mode": "default",
        "model_name": "모델",
        "results": [
            {
                "target": "국어/예시",
                "subject": "국어",
                "section": "예시",
                "model_name": "모델",
                "question_number": 1,
                "extracted_answer": 1,
                "correct_answer": 1,
                "is_correct": True,
                "points": 2,
                "answer_status": "answered",
                "complete": True,
                "provenance": "imported_public",
            }
        ],
    }
    model_verified_path(index, "모델").parent.mkdir(parents=True, exist_ok=True)
    model_verified_path(index, "모델").write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    save_verified(
        {
            "schema_version": 1,
            "exam_id": "example-text",
            "mode": "default",
            "selected_models": ["모델"],
            "results": [
                {
                    "target": "국어/예시",
                    "subject": "국어",
                    "section": "예시",
                    "model_name": "모델",
                    "question_number": 2,
                    "extracted_answer": 2,
                    "correct_answer": 2,
                    "is_correct": True,
                    "points": 2,
                    "answer_status": "answered",
                    "complete": True,
                    "provenance": "graded",
                }
            ],
        },
        index,
    )
    loaded = load_verified(index)
    assert {row["question_number"] for row in loaded["results"]} == {1, 2}
    assert json.loads(model_verified_path(index, "모델").read_text(encoding="utf-8"))["schema_version"] == 1


def test_cli_passes_canonical_path_and_preserves_imported_verified_only_row(tmp_path: Path):
    """CLI canonical 경로 전달과 raw 없는 imported verified 결과 보존 검증."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "questions.json").write_text(
        json.dumps(
            {
                "subject": "국어",
                "section": "예시",
                "questions": [
                    {"number": 1, "correct_answer": 2, "points": 2, "question_text": "본문"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "exam.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "cli-regression",
                "title": "CLI 회귀",
                "data_dir": "data",
                "results_dir": "results",
                "sections": [
                    {
                        "target": "국어/예시",
                        "subject": "국어",
                        "section": "예시",
                        "group": "국어",
                        "kind": "common",
                        "questions": "questions.json",
                        "max_points": 2,
                    }
                ],
                "modes": [{"id": "easy", "label": "쉬움", "input_mode": "question"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    exam = load_exam(manifest_path, project_root=tmp_path)
    run = create_run(
        exam_id=exam.id,
        mode="easy",
        input_mode="question",
        selected_targets=["국어/예시"],
        selected_models=[{"name": "모델", "model_id": "mock"}],
        input_context=[{"target": "국어/예시", "question_numbers": [1]}],
    )
    index = exam.results_root / "easy" / "results.json"
    save_run(run, index)
    verified_path = model_verified_path(index, "모델")
    verified_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exam_id": exam.id,
                "mode": "easy",
                "model_name": "모델",
                "results": [
                    {
                        "target": "국어/예시",
                        "subject": "국어",
                        "section": "예시",
                        "model_name": "모델",
                        "question_number": 1,
                        "extracted_answer": 2,
                        "correct_answer": 2,
                        "is_correct": True,
                        "points": 2,
                        "answer_status": "answered",
                        "complete": True,
                        "provenance": "imported_public",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _NoCallVerifier:
        def verify_answer(self, *args):
            raise AssertionError("imported verified-only 결과에는 추출기를 호출하면 안 됩니다.")

    seen_run_arguments = []

    def _grade_spy(run_argument, *args, **kwargs):
        seen_run_arguments.append(run_argument)
        return evaluation.grade_run(run_argument, *args, **kwargs)

    with patch.object(verify_answers, "build_verifier", return_value=_NoCallVerifier()), patch.object(
        verify_answers, "grade_run", side_effect=_grade_spy
    ):
        assert verify_answers.main(["--exam", str(manifest_path), "--easy"]) == 0

    assert seen_run_arguments == [index]
    saved = json.loads(verified_path.read_text(encoding="utf-8"))
    assert saved["results"][0]["provenance"] == "imported_public"
