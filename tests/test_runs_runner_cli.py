"""단일 생성 실행기와 공개 CLI의 집중 검증."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from csat_benchmark.cli import api_main
from csat_benchmark.exams import load_exam
from csat_benchmark.models import APIResponse, ModelConfig, Question
from csat_benchmark.runner import (
    _merge_contexts,
    _validate_prepared_media,
    run_exam,
    select_sections,
)
from csat_benchmark.runs import (
    RunStore,
    create_run,
    eligible_results,
    model_results_path,
    model_verified_path,
    result_is_completed,
    save_run,
)


def test_runner_preflight_allows_image_for_text_only_model() -> None:
    """@description 이미지 미지원 모델의 이미지 문항 사전 검증 통과 확인"""
    question = Question(
        number=1,
        correct_answer=1,
        points=2,
        question_text="본문",
        image_paths=["문항.png"],
    )
    config = ModelConfig(
        name="텍스트 모델",
        api_type="openai",
        api_key="test-key",
        model_id="test-model",
        supports_vision=False,
    )

    _validate_prepared_media({"국어/예시": [(question, 1)]}, {config.name: config})


class _FakeClient:
    """고정 응답을 반환하는 유료 호출 없는 공급자 대역."""

    def __init__(self, config, responses, calls):
        self.config = config
        self._responses = responses
        self._calls = calls
        self._lock = threading.Lock()

    def send_request(self, question):
        with self._lock:
            index = len(self._calls)
            self._calls.append(question.number)
        response = self._responses[index]
        if isinstance(response, dict):
            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response=response.get("raw_response", ""),
                timestamp="2026-09-07T00:00:00+00:00",
                success=response.get("success", False),
                error_message=response.get("error_message"),
                answer_status=response.get("answer_status"),
                provider_stop_reason=response.get("provider_stop_reason"),
            )
        return APIResponse(
            question_number=question.number,
            model_name=self.config.name,
            raw_response=response[0],
            timestamp="2026-09-07T00:00:00+00:00",
            success=response[1],
            error_message=None if response[1] else "모의 전송 실패",
            answer_status=None if response[1] else "technical_failure",
        )


class RunLayerTest(unittest.TestCase):
    """단일 생성·재시도·선택 범위를 검증한다."""

    def _config(self, root: Path, *names: str) -> Path:
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "system_prompt": "예시 시스템 지시",
                    "models": [
                        {
                            "name": name,
                            "api_type": "openai",
                            "api_key_env": "RUN_LAYER_TEST_KEY",
                            "model_id": f"mock-{index}",
                            "concurrent_request_limit": 1,
                            "batch_supported": False,
                        }
                        for index, name in enumerate(names)
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return config_path

    def _manifest(self, root: Path, *, question_count: int = 2) -> Path:
        """@description 문항별·섹션 묶음 모드가 있는 임시 시험 생성"""
        data_dir = root / "data"
        data_dir.mkdir()
        questions = [
            {
                "number": number,
                "correct_answer": 1,
                "points": 1,
                "question_text": f"문항 {number}",
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
                    "id": "runner-test",
                    "title": "실행 시험",
                    "short_name": "실행 시험",
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

    def test_question_selection_skips_unselected_missing_file(self) -> None:
        """@description 선택 문항만 본문·미디어 파일 검증 대상에 포함"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = self._manifest(root, question_count=2)
            question_path = root / "data" / "questions.json"
            question_path.write_text(
                json.dumps(
                    {
                        "subject": "국어",
                        "section": "예시",
                        "questions": [
                            {"number": 1, "correct_answer": 1, "points": 1, "question_text": "문항 1"},
                            {
                                "number": 2,
                                "correct_answer": 1,
                                "points": 1,
                                "question_path": "없는 문항.txt",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            exam = load_exam(manifest_path, project_root=root)
            config_path = self._config(root, "모델")
            calls: list[int] = []

            def factory(config, *, system_prompt):
                return _FakeClient(config, [("응답", True)], calls)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                result = run_exam(
                    exam,
                    config_path=config_path,
                    easy=True,
                    question_numbers=[1],
                    client_factory=factory,
                )
            self.assertEqual([1], calls)
            self.assertEqual([1], [row["question_number"] for row in result["results"]])

    def test_cli_unknown_target_returns_two_without_traceback(self) -> None:
        """@description 등록되지 않은 target의 CLI 오류 코드 2 반환"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = self._manifest(root, question_count=1)
            config_path = self._config(root, "모델")
            output = StringIO()
            errors = StringIO()
            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                with redirect_stdout(output), redirect_stderr(errors):
                    result = api_main(
                        [
                            "--exam",
                            str(manifest_path),
                            "--config",
                            str(config_path),
                            "--targets",
                            "없는/섹션",
                            "--check",
                        ]
                    )
            self.assertEqual(2, result)
            self.assertIn("오류:", errors.getvalue())
            self.assertNotIn("Traceback", errors.getvalue())

    def test_progress_reports_failure_and_empty_retry(self) -> None:
        """@description 실패 응답·작업 없는 재시도의 진행 상황 즉시 출력"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root, question_count=1), project_root=root)
            config_path = self._config(root, "모델")
            failure_output = StringIO()
            calls: list[int] = []

            def failure_factory(config, *, system_prompt):
                return _FakeClient(config, [("", False)], calls)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                with redirect_stdout(failure_output):
                    run_exam(exam, config_path=config_path, client_factory=failure_factory)
            self.assertIn("준비된 작업", failure_output.getvalue())
            self.assertIn("[1/1] 실패", failure_output.getvalue())
            self.assertIn("영역=국어/예시", failure_output.getvalue())
            self.assertNotIn("문항=0", failure_output.getvalue())
            self.assertIn("소요=", failure_output.getvalue())
            self.assertIn("오류=모의 전송 실패", failure_output.getvalue())

            success_output = StringIO()
            success_calls: list[int] = []

            def success_factory(config, *, system_prompt):
                return _FakeClient(config, [("응답", True)], success_calls)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                run_exam(exam, config_path=config_path, client_factory=success_factory)
                with redirect_stdout(success_output):
                    run_exam(
                        exam,
                        config_path=config_path,
                        retry_failed=True,
                        client_factory=success_factory,
                    )
            self.assertIn("작업 수=0", success_output.getvalue())
            self.assertIn("준비된 작업이 없습니다.", success_output.getvalue())

    def test_progress_is_printed_before_a_later_request_finishes(self) -> None:
        """@description 후속 요청 대기 중 선행 완료 진행 출력 관찰"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root, question_count=2), project_root=root)
            config_path = self._config(root, "모델")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["models"][0]["concurrent_request_limit"] = 2
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            second_started = threading.Event()
            release_second = threading.Event()
            first_progress = threading.Event()

            class _ProgressBuffer(StringIO):
                """@description 첫 완료 출력 관찰용 문자열 버퍼"""

                def write(self, value: str) -> int:
                    written = super().write(value)
                    if "[1/2] 성공" in self.getvalue():
                        first_progress.set()
                    return written

            output = _ProgressBuffer()

            class _BlockingClient:
                """@description 두 번째 요청을 대기시키는 공급자 대역"""

                def send_request(self, question):
                    if question.number == 2:
                        second_started.set()
                        release_second.wait(timeout=5)
                    return APIResponse(
                        question_number=question.number,
                        model_name="모델",
                        raw_response="응답",
                        timestamp="2026-09-07T00:00:00+00:00",
                        success=True,
                    )

            result_holder: list[dict] = []
            errors: list[BaseException] = []

            def factory(config, *, system_prompt):
                return _BlockingClient()

            def run():
                """@description 대기 요청 실행 스레드"""
                try:
                    result_holder.append(
                        run_exam(
                            exam,
                            config_path=config_path,
                            easy=True,
                            client_factory=factory,
                        )
                    )
                except BaseException as error:
                    errors.append(error)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                with redirect_stdout(output):
                    worker = threading.Thread(target=run)
                    worker.start()
                    second_seen = second_started.wait(timeout=5)
                    first_seen = first_progress.wait(timeout=5)
                    output_before_release = output.getvalue()
                    worker_running = worker.is_alive()
                    release_second.set()
                    worker.join(timeout=5)

            self.assertTrue(second_seen)
            self.assertTrue(first_seen)
            self.assertTrue(worker_running)
            self.assertIn("[1/2] 성공", output_before_release)
            self.assertFalse(errors)
            self.assertFalse(worker.is_alive())
            self.assertEqual(2, len(result_holder[0]["results"]))

    def test_default_runs_one_section_generation_and_easy_runs_questions(self) -> None:
        """일반 mode는 섹션 한 번, --easy는 문항별 한 번씩 호출한다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root), project_root=root)
            config_path = self._config(root, "모델")
            calls: list[int] = []

            def factory(config, *, system_prompt):
                return _FakeClient(config, [("응답", True)] * 4, calls)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                normal = run_exam(exam, config_path=config_path, client_factory=factory)
                easy = run_exam(exam, config_path=config_path, easy=True, client_factory=factory)
            self.assertEqual([0, 1, 2], calls)
            self.assertEqual("section", normal["input_mode"])
            self.assertEqual("question", easy["input_mode"])
            self.assertEqual(1, len([row for row in normal["results"] if row["question_number"] == 0]))
            self.assertEqual({1, 2}, {row["question_number"] for row in easy["results"]})

    def test_merge_contexts_preserves_metadata_question_numbers(self) -> None:
        """문항 기록이 없는 기존 문맥의 전체 문항 번호를 부분 실행 뒤에도 보존한다."""
        target = "국어/예시"
        stored = [
            {
                "target": target,
                "subject": "국어",
                "section": "예시",
                "input_mode": "question",
                "question_numbers": [1, 2],
            }
        ]
        partial = [
            {
                "target": target,
                "question_numbers": [1],
                "questions": [{"number": 1, "question_text": "문항 1"}],
            }
        ]
        merged = _merge_contexts(stored, partial)
        self.assertEqual([1, 2], merged[0]["question_numbers"])

        expanded = _merge_contexts(
            merged,
            [
                {
                    "target": target,
                    "question_numbers": [3],
                    "questions": [{"number": 3, "question_text": "문항 3"}],
                }
            ],
        )
        self.assertEqual([1, 2, 3], expanded[0]["question_numbers"])

    def test_retry_failed_replaces_only_technical_failure(self) -> None:
        """재시도는 누락·기술 실패만 교체하고 완료 결과를 보존한다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root, question_count=1), project_root=root)
            config_path = self._config(root, "모델")
            calls: list[int] = []
            responses = [("", False), ("성공", True), ("재시도", True)]

            def factory(config, *, system_prompt):
                return _FakeClient(config, responses, calls)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                first = run_exam(exam, config_path=config_path, client_factory=factory)
                retried = run_exam(
                    exam,
                    config_path=config_path,
                    retry_failed=True,
                    client_factory=factory,
                )
            self.assertEqual([0, 0], calls)
            self.assertEqual("성공", retried["results"][0]["raw_response"])
            self.assertTrue(result_is_completed(retried["results"][0]))
            self.assertNotIn("run_id", first)

    def test_retry_preserves_refusal_without_calling_provider(self) -> None:
        """거부 응답은 완료 결과로 보아 기술 재시도에서 보존한다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root, question_count=1), project_root=root)
            config_path = self._config(root, "모델")
            calls: list[int] = []
            responses = [
                {
                    "success": False,
                    "raw_response": "답변할 수 없습니다.",
                    "answer_status": "refusal",
                    "provider_stop_reason": "refusal",
                    "error_message": "거부",
                },
                ("불필요한 재시도", True),
            ]

            def factory(config, *, system_prompt):
                return _FakeClient(config, responses, calls)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                first = run_exam(exam, config_path=config_path, client_factory=factory)
                retried = run_exam(exam, config_path=config_path, retry_failed=True, client_factory=factory)
            self.assertEqual([0], calls)
            self.assertEqual("답변할 수 없습니다.", retried["results"][0]["raw_response"])
            self.assertEqual(1, len(eligible_results(first)))

    def test_new_models_initialize_sidecars_before_union_index_publish(self) -> None:
        """기존 모델 뒤에 추가한 여러 모델의 빈 원본을 첫 저장 전에 준비한다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root, question_count=1), project_root=root)
            config_path = self._config(root, "모델 A")
            calls = {"모델 A": [], "모델 B": [], "모델 C": []}

            def factory(config, *, system_prompt):
                return _FakeClient(config, [(config.name, True)], calls[config.name])

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                run_exam(exam, config_path=config_path, client_factory=factory)
                self._config(root, "모델 A", "모델 B", "모델 C")
                run_exam(
                    exam,
                    config_path=config_path,
                    model_names=["모델 B", "모델 C"],
                    client_factory=factory,
                )
            index = exam.results_root / "default" / "results.json"
            loaded = RunStore.load(index).run
            self.assertEqual(
                {"모델 A", "모델 B", "모델 C"},
                {model["name"] for model in loaded["selected_models"]},
            )
            self.assertTrue(calls["모델 A"])
            self.assertTrue(calls["모델 B"])
            self.assertTrue(calls["모델 C"])
            for model_name in calls:
                self.assertTrue(model_results_path(index, model_name).is_file())

    def test_verified_only_section_is_complete_without_fabricating_raw(self) -> None:
        """raw 없이 section verified 결과가 모두 완료면 재시도하지 않는다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root, question_count=2), project_root=root)
            config_path = self._config(root, "모델")
            index = exam.results_root / "default" / "results.json"
            run = create_run(
                exam_id=exam.id,
                mode="default",
                input_mode="section",
                selected_targets=["국어/예시"],
                selected_models=[{"name": "모델", "model_id": "mock"}],
                input_context=[{"target": "국어/예시", "question_numbers": [1, 2]}],
            )
            save_run(run, index)
            model_results_path(index, "모델").unlink()
            verified = {
                "exam_id": exam.id,
                "mode": "default",
                "model_name": "모델",
                "results": [
                    {"target": "국어/예시", "model_name": "모델", "question_number": 1, "complete": True},
                    {"target": "국어/예시", "model_name": "모델", "question_number": 2, "complete": True},
                ],
            }
            model_verified_path(index, "모델").write_text(json.dumps(verified, ensure_ascii=False), encoding="utf-8")
            calls: list[int] = []

            def factory(config, *, system_prompt):
                return _FakeClient(config, [("호출 금지", True)], calls)

            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                retried = run_exam(exam, config_path=config_path, retry_failed=True, client_factory=factory)
            self.assertEqual([], calls)
            self.assertEqual([], retried["results"])
            self.assertFalse(model_results_path(index, "모델").exists())

    def test_regeneration_invalidates_verified_before_failed_replacement(self) -> None:
        """기존 verified를 지운 뒤 기술 실패 원본도 정본에 저장한다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            exam = load_exam(self._manifest(root, question_count=1), project_root=root)
            config_path = self._config(root, "모델")
            calls: list[int] = []

            def factory(config, *, system_prompt):
                return _FakeClient(config, [("", False)], calls)

            index = exam.results_root / "default" / "results.json"
            initial = create_run(
                exam_id=exam.id,
                mode="default",
                input_mode="section",
                selected_targets=["국어/예시"],
                selected_models=[{"name": "모델", "model_id": "mock"}],
            )
            save_run(initial, index)
            model_verified_path(index, "모델").write_text(
                json.dumps(
                    {
                        "exam_id": exam.id,
                        "mode": "default",
                        "model_name": "모델",
                        "results": [
                            {"target": "국어/예시", "model_name": "모델", "question_number": 1, "complete": True}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"RUN_LAYER_TEST_KEY": "test-key"}):
                run_exam(exam, config_path=config_path, client_factory=factory)
            self.assertEqual([], json.loads(model_verified_path(index, "모델").read_text(encoding="utf-8"))["results"])
            self.assertEqual([0], calls)

    def test_selection_and_manifest_modes_follow_public_contract(self) -> None:
        """선택자 보존·전체 시험 기본 선택·매니페스트 attempts 제거를 확인한다."""
        exam = load_exam("csat-2026")
        self.assertEqual(13, len(select_sections(exam)))
        self.assertEqual(13, len(select_sections(exam, benchmark_all=True)))
        self.assertEqual({"default", "easy"}, {mode.id for mode in exam.modes})
        self.assertTrue(all(not hasattr(mode, "attempts") for mode in exam.modes))

    def test_cli_requires_exam_and_removes_old_mode_flags(self) -> None:
        """실행에는 --exam이 필요하고 구형 --run·--mode 인자를 받지 않는다."""
        with self.assertRaises(SystemExit):
            api_main([])
        with self.assertRaises(SystemExit):
            api_main(["--exam", "example-text", "--mode", "default"])
        with self.assertRaises(SystemExit):
            api_main(["--exam", "example-text", "--run", "old"])

    def test_cli_check_uses_easy_without_provider_call(self) -> None:
        """--check와 --easy 선택은 공급자 생성 없이 입력을 검사한다."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = self._manifest(root, question_count=1)
            config_path = self._config(root, "모델")
            output = StringIO()
            with patch("csat_benchmark.cli.run_exam", side_effect=AssertionError("호출 금지")):
                with redirect_stdout(output):
                    result = api_main(
                        [
                            "--exam",
                            str(manifest_path),
                            "--config",
                            str(config_path),
                            "--easy",
                            "--check",
                        ]
                    )
            self.assertEqual(0, result)
            self.assertIn("easy", output.getvalue())


if __name__ == "__main__":
    unittest.main()
