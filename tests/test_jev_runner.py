"""Jev CLI 연결과 공용 실행기 재사용을 검증한다."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from csat_benchmark.cli import _build_parser
from csat_benchmark.exams import load_exam
from csat_benchmark.models import APIResponse
from csat_benchmark.runs import RunStore
from csat_benchmark.runner import RunnerError
from csat_benchmark.jev_runner import check_jev_exam, run_jev_exam
from jev_solver import main


def _write_config(path: Path, *model_names: str, verifier: bool = False) -> Path:
    models = [
        {
            "name": name,
            "api_type": "jev",
            "model_id": "typesafe/jev-1.13",
            "api_key_env": "OPENROUTER_API_KEY",
            "supports_vision": False,
            "concurrent_request_limit": 1,
            "batch_supported": False,
        }
        for name in model_names
    ]
    config = {"models": models}
    if verifier:
        config["verifier"] = {"name": "검증기", "api_key_env": "MISSING_VERIFIER_KEY"}
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def _write_exam(root: Path, question_count: int = 2) -> Path:
    data_dir = root / "data"
    data_dir.mkdir()
    questions = [
        {
            "number": number,
            "correct_answer": 1,
            "points": 1,
            "question_text": f"원문 문항 {number}",
        }
        for number in range(1, question_count + 1)
    ]
    (data_dir / "questions.json").write_text(
        json.dumps({"subject": "국어", "section": "예시", "questions": questions}, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_path = root / "exam.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "jev-runner-test",
                "title": "Jev 실행 시험",
                "short_name": "Jev 실행 시험",
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
                        "max_points": question_count,
                    }
                ],
                "modes": [
                    {"id": "default", "label": "일반", "input_mode": "section"},
                    {"id": "easy", "label": "쉬움", "input_mode": "question"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


class _FakeJevClient:
    def __init__(self, config, *, system_prompt, calls):
        self.config = config
        self.calls = calls

    def send_questions(self, question, *, subject, questions):
        self.calls.append(
            {
                "model": self.config.name,
                "question_number": question.number,
                "subject": subject,
                "questions": questions,
            }
        )
        return APIResponse(
            question_number=question.number,
            model_name=self.config.name,
            raw_response=f"응답 {self.config.name} {question.number}",
            timestamp="2026-09-28T00:00:00+00:00",
            success=True,
        )


def test_jev_parser_matches_api_parser_flags_with_jev_default(tmp_path: Path) -> None:
    ordinary = _build_parser(tmp_path)
    jev = _build_parser(tmp_path, default_config_filename="jev_config.json")

    ordinary_flags = [action.option_strings for action in ordinary._actions if action.dest != "help"]
    jev_flags = [action.option_strings for action in jev._actions if action.dest != "help"]

    assert jev_flags == ordinary_flags
    assert ordinary.get_default("config") == str(tmp_path / "config.json")
    assert jev.get_default("config") == str(tmp_path / "jev_config.json")


def test_jev_list_and_check_need_no_api_or_verifier_key_and_make_no_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path / "jev_config.json", "Jev 1.13", verifier=True)
    exam_path = _write_exam(tmp_path, question_count=1)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MISSING_VERIFIER_KEY", raising=False)
    output = StringIO()

    with patch("csat_benchmark.jev_runner.JevClient", side_effect=AssertionError("API 호출 금지")):
        with redirect_stdout(output):
            assert main(["--config", str(config_path), "--list-models"]) == 0
            assert main(
                ["--exam", str(exam_path), "--config", str(config_path), "--check"]
            ) == 0

    assert "Jev 1.13" in output.getvalue()
    assert "검증 완료" in output.getvalue()


def test_jev_sender_forwards_all_section_questions_and_only_matching_easy_question(
    tmp_path: Path,
    monkeypatch,
) -> None:
    exam_path = _write_exam(tmp_path)
    exam = load_exam(exam_path, project_root=tmp_path)
    config_path = _write_config(tmp_path / "jev_config.json", "Jev 1.13")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = []

    def client_factory(config, *, system_prompt):
        return _FakeJevClient(config, system_prompt=system_prompt, calls=calls)

    with patch("csat_benchmark.jev_runner.JevClient", side_effect=client_factory):
        run_jev_exam(exam, config_path=config_path)
        run_jev_exam(exam, config_path=config_path, easy=True)

    section_call = next(call for call in calls if call["question_number"] == 0)
    assert section_call["subject"] == "국어"
    assert section_call["questions"] == [
        {"number": 1, "question_text": "원문 문항 1"},
        {"number": 2, "question_text": "원문 문항 2"},
    ]
    easy_calls = [call for call in calls if call["question_number"]]
    assert [call["question_number"] for call in easy_calls] == [1, 2]
    for call in easy_calls:
        assert call["questions"] == [
            {"number": call["question_number"], "question_text": f"원문 문항 {call['question_number']}"}
        ]
        assert set(call["questions"][0]) == {"number", "question_text"}


def test_jev_retry_only_retries_technical_failure_and_keeps_other_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    exam_path = _write_exam(tmp_path)
    exam = load_exam(exam_path, project_root=tmp_path)
    config_path = _write_config(tmp_path / "jev_config.json", "Jev A", "Jev B")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = []

    class RetryClient:
        def __init__(self, config, *, system_prompt):
            self.config = config

        def send_questions(self, question, *, subject, questions):
            calls.append((self.config.name, question.number))
            is_first_question_attempt = question.number == 1 and calls.count((self.config.name, 1)) == 1
            is_second_model = self.config.name == "Jev B"
            if is_first_question_attempt and not is_second_model:
                return APIResponse(
                    question_number=question.number,
                    model_name=self.config.name,
                    raw_response="",
                    timestamp="2026-09-28T00:00:00+00:00",
                    success=False,
                    error_message="연결 실패",
                    answer_status="technical_failure",
                )
            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response="오답 응답이지만 완료",
                timestamp="2026-09-28T00:00:00+00:00",
                success=True,
            )

    with patch("csat_benchmark.jev_runner.JevClient", RetryClient):
        run_jev_exam(
            exam,
            config_path=config_path,
            model_names=["Jev A"],
            easy=True,
        )
        run_jev_exam(
            exam,
            config_path=config_path,
            model_names=["Jev B"],
            easy=True,
            merge=True,
        )
        retried = run_jev_exam(
            exam,
            config_path=config_path,
            model_names=["Jev A"],
            easy=True,
            retry_failed=True,
            merge=True,
        )

    assert calls.count(("Jev A", 1)) == 2
    assert calls.count(("Jev A", 2)) == 1
    assert calls.count(("Jev B", 1)) == 1
    assert calls.count(("Jev B", 2)) == 1
    assert {model["name"] for model in retried["selected_models"]} == {"Jev A", "Jev B"}
    assert {row["model_name"] for row in retried["results"]} == {"Jev A", "Jev B"}
    assert all(row["raw_response"] == "오답 응답이지만 완료" for row in retried["results"])
    canonical = tmp_path / "results" / "easy" / "results.json"
    assert RunStore.load(canonical).run["results"] == retried["results"]


def test_jev_configuration_rejects_other_api_types_or_vision(tmp_path: Path) -> None:
    exam_path = _write_exam(tmp_path, question_count=1)
    config_path = tmp_path / "jev_config.json"
    invalid_configs = [
        (
            {
                "name": "잘못된 API 모델",
                "api_type": "openai",
                "model_id": "test",
                "supports_vision": False,
            },
            "api_type은 jev",
        ),
        (
            {
                "name": "비전 지원 모델",
                "api_type": "jev",
                "model_id": "test",
                "supports_vision": True,
            },
            "supports_vision은 false",
        ),
    ]
    for model, error_message in invalid_configs:
        config_path.write_text(
            json.dumps({"models": [model]}),
            encoding="utf-8",
        )
        try:
            check_jev_exam(exam_path, config_path=config_path)
        except RunnerError as error:
            assert error_message in str(error)
        else:
            raise AssertionError(f"{error_message} 설정을 거부해야 합니다.")
