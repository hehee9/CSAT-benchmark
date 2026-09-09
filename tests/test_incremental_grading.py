"""@description 증분 채점 범위·재채점 선택·부분 섹션 입력 집중 검증"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from csat_benchmark.evaluation import grade_run
from csat_benchmark.exams import load_exam
from csat_benchmark.runs import create_run


def _make_exam(tmp_path: Path, *, mode: str, input_mode: str):
    """@description 두 문항 증분 채점 시험 생성"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "questions.json").write_text(
        json.dumps(
            {
                "subject": "국어",
                "section": "예시",
                "questions": [
                    {"number": 1, "correct_answer": 1, "points": 2, "question_text": "문항 1"},
                    {"number": 2, "correct_answer": 2, "points": 3, "question_text": "문항 2"},
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
                "id": f"incremental-{mode}",
                "title": "증분 채점 시험",
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
                        "max_points": 5,
                    }
                ],
                "modes": [{"id": mode, "label": mode, "input_mode": input_mode}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return load_exam(manifest_path, project_root=tmp_path)


def _make_run(exam, *, mode: str, input_mode: str, models: list[str]):
    """@description 증분 채점용 완료 원본 실행 생성"""
    run = create_run(
        exam_id=exam.id,
        mode=mode,
        input_mode=input_mode,
        selected_targets=["국어/예시"],
        selected_models=[{"name": model, "model_id": model} for model in models],
        input_context=[{"target": "국어/예시", "question_numbers": [1, 2]}],
    )
    run["results"] = []
    for model in models:
        if input_mode == "section":
            run["results"].append(
                {
                    "target": "국어/예시",
                    "subject": "국어",
                    "section": "예시",
                    "model_name": model,
                    "question_number": 0,
                    "success": True,
                    "raw_response": f"응답-{model}",
                    "answer_status": None,
                    "provider_stop_reason": None,
                }
            )
        else:
            for number in (1, 2):
                run["results"].append(
                    {
                        "target": "국어/예시",
                        "subject": "국어",
                        "section": "예시",
                        "model_name": model,
                        "question_number": number,
                        "success": True,
                        "raw_response": f"응답-{model}-{number}",
                        "answer_status": None,
                        "provider_stop_reason": None,
                    }
                )
    return run


def _verified_row(model: str, number: int, *, is_correct: bool = True) -> dict:
    """@description 기존 verified 행 생성"""
    return {
        "target": "국어/예시",
        "subject": "국어",
        "section": "예시",
        "model_name": model,
        "question_number": number,
        "extracted_answer": number,
        "correct_answer": number,
        "is_correct": is_correct,
        "points": 2 if number == 1 else 3,
        "answer_status": "answered",
        "complete": True,
        "provenance": "graded",
    }


class _EasyVerifier:
    """@description 문항별 pending 호출 기록 검증기 대역"""

    def __init__(self):
        self.calls: list[int] = []

    def verify_answer(self, raw_response, correct_answer, question_number, question_text):
        del raw_response, question_text
        self.calls.append(question_number)
        return correct_answer


class _HardVerifier:
    """@description pending 섹션 문항 정보와 원문 보존 검증기 대역"""

    def __init__(self):
        self.calls: list[tuple[str, list[int]]] = []

    def verify_hard_answers(self, raw_response, question_infos):
        self.calls.append((raw_response, [info["number"] for info in question_infos]))
        return [
            {
                "question_number": info["number"],
                "correct_answer": info["correct_answer"],
                "llm_answer": info["correct_answer"],
            }
            for info in question_infos
        ]


def test_default_grades_only_uncompleted_question_and_keeps_skipped_row(tmp_path: Path, capsys):
    """@description 기본 채점의 완료 행 건너뛰기 및 미완료 문항 호출 확인"""
    exam = _make_exam(tmp_path, mode="easy", input_mode="question")
    run = _make_run(exam, mode="easy", input_mode="question", models=["모델"])
    verifier = _EasyVerifier()

    graded = grade_run(
        run,
        exam,
        verifier,
        verified={"selected_models": ["모델"], "results": [_verified_row("모델", 1)]},
    )

    assert verifier.calls == [2, 2]
    assert {row["question_number"] for row in graded["results"]} == {1, 2}
    assert graded["score_by_model"] == {"모델": 5}
    assert "작업 1개, 건너뛴 문항 1개" in capsys.readouterr().out


def test_model_filter_all_complete_automatically_regrades_but_default_does_not(tmp_path: Path, capsys):
    """@description 모델 선택 시 전체 완료 범위 자동 재채점 및 기본 호출 보존 확인"""
    exam = _make_exam(tmp_path, mode="easy", input_mode="question")
    run = _make_run(exam, mode="easy", input_mode="question", models=["모델"])
    prior = {"selected_models": ["모델"], "results": [_verified_row("모델", 1), _verified_row("모델", 2)]}

    no_filter_verifier = _EasyVerifier()
    unchanged = grade_run(run, exam, no_filter_verifier, verified=prior)
    assert no_filter_verifier.calls == []
    assert unchanged["results"]

    filtered_verifier = _EasyVerifier()
    regraded = grade_run(run, exam, filtered_verifier, model_names=["모델"], verified=prior)
    assert sorted(filtered_verifier.calls) == [1, 1, 2, 2]
    assert regraded["results"]
    assert "재채점: 예" in capsys.readouterr().out


def test_update_regrades_only_selected_question(tmp_path: Path):
    """@description --update 지정 문항 범위 재채점 확인"""
    exam = _make_exam(tmp_path, mode="easy", input_mode="question")
    run = _make_run(exam, mode="easy", input_mode="question", models=["모델"])
    verifier = _EasyVerifier()

    graded = grade_run(
        run,
        exam,
        verifier,
        question_numbers=[2],
        update=True,
        verified={"selected_models": ["모델"], "results": [_verified_row("모델", 1), _verified_row("모델", 2)]},
    )

    assert verifier.calls == [2, 2]
    assert [row["question_number"] for row in graded["results"]] == [2]


def test_mixed_model_history_grades_only_uncompleted_scope(tmp_path: Path):
    """@description 혼합 모델 이력에서 완료 모델의 암묵적 재채점 방지 확인"""
    exam = _make_exam(tmp_path, mode="easy", input_mode="question")
    run = _make_run(exam, mode="easy", input_mode="question", models=["모델A", "모델B"])
    verifier = _EasyVerifier()

    graded = grade_run(
        run,
        exam,
        verifier,
        model_names=["모델A", "모델B"],
        verified={"selected_models": ["모델A", "모델B"], "results": [_verified_row("모델A", 1)]},
    )

    assert sorted(verifier.calls) == [1, 1, 2, 2, 2, 2]
    assert len(graded["results"]) == 4


def test_section_grading_sends_only_pending_infos_and_preserves_raw_response(tmp_path: Path):
    """@description 섹션 채점의 pending 문항 정보 및 원본 응답 보존 확인"""
    exam = _make_exam(tmp_path, mode="default", input_mode="section")
    run = _make_run(exam, mode="default", input_mode="section", models=["모델"])
    verifier = _HardVerifier()

    graded = grade_run(
        run,
        exam,
        verifier,
        verified={"selected_models": ["모델"], "results": [_verified_row("모델", 1)]},
    )

    assert verifier.calls == [("응답-모델", [2]), ("응답-모델", [2])]
    assert {row["question_number"] for row in graded["results"]} == {1, 2}
    assert graded["results"][-1]["raw_response"] == "응답-모델"


def test_cli_update_forwards_flag_to_grade_run(tmp_path: Path):
    """@description CLI --update 전달 및 결과 저장 호출 확인"""
    import verify_answers

    class _Verifier:
        """@description CLI 검증기 호출 대역"""

        model_id = "fake"
        reasoning_effort = "low"

    verified = {
        "score_by_model": {"모델": 0},
        "complete_by_model": {"모델": True},
        "results": [],
    }
    grade_calls: list[dict] = []
    save_calls: list[tuple[dict, Path]] = []
    run_path = tmp_path / "results.json"

    def _grade(*args, **kwargs):
        """@description CLI 채점 호출 기록"""
        grade_calls.append(kwargs)
        return verified

    def _save(payload, path):
        """@description CLI 저장 호출 기록"""
        save_calls.append((payload, path))

    with patch.object(verify_answers, "resolve_run", return_value=("exam", "default", {}, run_path)), patch.object(
        verify_answers, "build_verifier", return_value=_Verifier()
    ), patch.object(verify_answers, "grade_run", side_effect=_grade), patch.object(
        verify_answers, "save_verified", side_effect=_save
    ):
        assert verify_answers.main(["--exam", "exam-id", "--update"]) == 0

    assert grade_calls[0]["update"] is True
    assert save_calls == [(verified, run_path)]
