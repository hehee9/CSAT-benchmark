"""공통 모델·설정·시험 매니페스트의 집중 검증."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from csat_benchmark import (
    APIResponse,
    ConfigurationError,
    load_config,
    load_exam,
    load_section_questions,
    list_exams,
)
from csat_benchmark.evaluation import build_verifier
from csat_benchmark.runner import run_exam


class FoundationTest(unittest.TestCase):
    """기초 자료 계층의 사용자-visible 계약 검증."""

    def test_config_resolves_dotenv_without_overriding_process_environment(self) -> None:
        """환경 변수 인증 정보 해석과 선택 모델 필터를 검증."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".env").write_text(
                "FOUNDATION_DOTENV_KEY=from-dotenv\nFOUNDATION_SECOND_KEY=second\n",
                encoding="utf-8",
            )
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "models": [
                            {
                                "name": "첫 모델",
                                "api_type": "openai",
                                "api_key_env": "FOUNDATION_DOTENV_KEY",
                                "model_id": "example-one",
                            },
                            {
                                "name": "둘째 모델",
                                "api_type": "openai",
                                "api_key_env": [
                                    "FOUNDATION_DOTENV_KEY",
                                    "FOUNDATION_SECOND_KEY",
                                ],
                                "model_id": "example-two",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.environ["FOUNDATION_DOTENV_KEY"] = "from-process"
            try:
                metadata = load_config(config_path, resolve_secrets=False)
                self.assertEqual(["첫 모델", "둘째 모델"], [m["name"] for m in metadata["models"]])
                self.assertNotIn("api_key", metadata["models"][0])
                self.assertEqual(
                    ["둘째 모델"],
                    [m["name"] for m in load_config(config_path, model_names=["둘째 모델"])["models"]],
                )
                resolved = load_config(config_path)
                self.assertEqual("from-process", resolved["models"][0]["api_key"])
                self.assertEqual(
                    ["from-process", "second"],
                    resolved["models"][1]["api_key"],
                )
                with self.assertRaisesRegex(ValueError, "등록되지 않은 모델"):
                    load_config(config_path, model_names=["없는 모델"])
                os.environ["FOUNDATION_DOTENV_KEY"] = ""
                with self.assertRaisesRegex(ConfigurationError, "FOUNDATION_DOTENV_KEY"):
                    load_config(config_path, model_names=["첫 모델"])
            finally:
                os.environ.pop("FOUNDATION_DOTENV_KEY", None)
                os.environ.pop("FOUNDATION_SECOND_KEY", None)

    def test_verifier_secret_resolution_is_opt_in_and_separate(self) -> None:
        """@description 모델·verifier 인증 정보 해석 범위 분리"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "models": [
                            {
                                "name": "모델",
                                "api_type": "openai",
                                "api_key_env": "FOUNDATION_MODEL_KEY",
                                "model_id": "example-model",
                            }
                        ],
                        "verifier": {
                            "api_key_env": "FOUNDATION_VERIFIER_KEY",
                            "model_id": "example-verifier",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FOUNDATION_MODEL_KEY": "model-key"}, clear=False):
                os.environ.pop("FOUNDATION_VERIFIER_KEY", None)
                resolved = load_config(config_path, model_names=["모델"])
                self.assertEqual("model-key", resolved["models"][0]["api_key"])
                self.assertNotIn("api_key", resolved["verifier"])

                class _GenerationClient:
                    """@description 생성 호출 검증용 공급자 대역"""

                    def send_request(self, question):
                        return APIResponse(
                            question_number=question.number,
                            model_name="모델",
                            raw_response="응답",
                            timestamp="2026-09-07T00:00:00+00:00",
                            success=True,
                        )

                generated = run_exam(
                    load_exam("example-text"),
                    config_path=config_path,
                    output=root / "results.json",
                    client_factory=lambda config, *, system_prompt: _GenerationClient(),
                )
                self.assertEqual(1, len(generated["results"]))
                with self.assertRaisesRegex(ConfigurationError, "FOUNDATION_VERIFIER_KEY"):
                    build_verifier(config_path)

    def test_manifest_supports_variable_section_catalog_and_public_example(self) -> None:
        """13개 실제 섹션과 공개 텍스트 예시의 경로·실행 정책을 검증."""
        exam = load_exam("csat-2026")
        self.assertEqual(13, len(exam.sections))
        self.assertEqual("2026 수능", exam.short_name)
        self.assertEqual("2025-11", exam.exam_month)
        self.assertIn("탐구/물리1", {section.target for section in exam.sections})
        self.assertEqual({"default", "easy"}, {mode.id for mode in exam.modes})
        self.assertEqual("hard_all_results.json", exam.modes[0].public_results)
        self.assertEqual("all_results.json", exam.modes[1].public_results)

        preparation = load_exam("csat-2027")
        self.assertEqual(26, len(preparation.sections))
        self.assertEqual(
            {
                "생활과윤리",
                "윤리와사상",
                "한국지리",
                "세계지리",
                "동아시아사",
                "세계사",
                "경제",
                "정치와법",
                "사회문화",
                "물리1",
                "물리2",
                "화학1",
                "화학2",
                "생명1",
                "생명2",
                "지구1",
                "지구2",
            },
            {section.subject for section in preparation.sections[-17:]},
        )

        example = load_exam("example-text")
        self.assertFalse(example.publish)
        self.assertEqual(example.title, example.short_name)
        self.assertIsNone(example.exam_month)
        self.assertEqual("section", example.modes[0].input_mode)
        questions = load_section_questions(example, "국어/예시")
        self.assertEqual(1, len(questions))
        self.assertEqual(2, questions[0].correct_answer)
        self.assertTrue(questions[0].load_question_text())
        self.assertEqual({"csat-2026", "csat-2027", "example-text"}, {e.id for e in list_exams()})

    def test_empty_success_response_is_normalized(self) -> None:
        """본문과 토큰이 없는 성공 응답의 기존 실패 정규화를 검증."""
        response = APIResponse(1, "예시 모델", "", "2026-01-01T00:00:00Z", True)
        self.assertFalse(response.success)
        self.assertEqual("no_answer", response.answer_status)
        self.assertIsNotNone(response.error_message)


if __name__ == "__main__":
    unittest.main()
