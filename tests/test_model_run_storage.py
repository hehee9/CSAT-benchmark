"""정본 실행 색인과 모델별 원본 저장 형식의 집중 검증."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import csat_benchmark.runs as run_storage
from csat_benchmark.runs import (
    RUN_SCHEMA_VERSION,
    canonical_results_path,
    create_run,
    invalidate_verified_results,
    load_run,
    model_results_path,
    model_verified_path,
    save_run,
    upsert_result,
    verified_result_is_completed,
)


class ModelRunStorageTest(unittest.TestCase):
    """정본 색인·모델 원본·검증 결과 연계를 검증한다."""

    def _run(self, *model_names: str, input_mode: str = "section") -> dict:
        """@description 고정 정본 실행 문서 생성"""
        return create_run(
            exam_id="example-text",
            mode="default",
            input_mode=input_mode,
            selected_targets=["국어/예시"],
            selected_models=[
                {"name": name, "model_id": f"id-{index}"}
                for index, name in enumerate(model_names)
            ],
            created_at="2026-09-07T00:00:00+00:00",
        )

    def _result(
        self,
        model_name: str,
        *,
        question_number: int = 0,
        raw_response: str = "응답",
        success: bool = True,
    ) -> dict:
        """@description 고정 결과 문서 생성"""
        return {
            "target": "국어/예시",
            "subject": "국어",
            "section": "예시",
            "model_name": model_name,
            "question_number": question_number,
            "raw_response": raw_response,
            "timestamp": "2026-09-07T00:00:00+00:00",
            "success": success,
            "error_message": None if success else "기술 실패",
            "input_tokens": 1 if success else None,
            "output_tokens": 1 if success else None,
            "total_tokens": 2 if success else None,
            "answer_status": None if success else "technical_failure",
            "provider_stop_reason": None,
            "error_details": None,
        }

    def test_canonical_model_and_verified_paths_are_stable(self) -> None:
        """@description canonical 색인·원본·검증 경로 안정성 확인"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            index = canonical_results_path(root, "default")
            self.assertEqual(root / "default" / "results.json", index)
            self.assertEqual(
                root / "default" / "models" / model_results_path(index, "A/B").parent.name / "results.json",
                model_results_path(index, "A/B"),
            )
            self.assertEqual(
                model_results_path(index, "A/B").parent / "verified.json",
                model_verified_path(index, "A/B"),
            )
            self.assertNotEqual(model_results_path(index, "A/B"), model_results_path(index, "A\\B"))

    def test_common_metadata_and_model_sidecars_have_no_execution_id_or_attempt(self) -> None:
        """@description 정본 메타데이터·모델별 결과의 단일 생성 계약 확인"""
        run = self._run("첫 모델", "둘째 모델")
        run["results"] = [
            self._result("둘째 모델", raw_response="둘째 응답"),
            self._result("첫 모델", raw_response="첫 응답"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            index = Path(temporary_directory) / "default" / "results.json"
            save_run(run, index)
            common = json.loads(index.read_text(encoding="utf-8"))
            self.assertEqual(RUN_SCHEMA_VERSION, common["schema_version"])
            self.assertNotIn("results", common)
            self.assertNotIn("run_id", common)
            self.assertNotIn("attempts_expected", common)
            self.assertEqual({"첫 모델", "둘째 모델"}, set(common["model_results"]))
            for model_name in common["model_results"]:
                sidecar = json.loads(model_results_path(index, model_name).read_text(encoding="utf-8"))
                self.assertEqual(run["exam_id"], sidecar["exam_id"])
                self.assertEqual(run["mode"], sidecar["mode"])
                self.assertEqual(model_name, sidecar["model_name"])
                self.assertTrue(all("attempt" not in row for row in sidecar["results"]))
            loaded = load_run(index)
        self.assertEqual(
            {("둘째 모델", "둘째 응답"), ("첫 모델", "첫 응답")},
            {(row["model_name"], row["raw_response"]) for row in loaded["results"]},
        )

    def test_upsert_replaces_identity_and_writes_changed_model_only(self) -> None:
        """@description 동일 key 교체와 변경 모델 단독 갱신 확인"""
        run = self._run("모델 A", "모델 B")
        with tempfile.TemporaryDirectory() as temporary_directory:
            index = Path(temporary_directory) / "default" / "results.json"
            save_run(run, index)
            model_b_path = model_results_path(index, "모델 B")
            model_b_before = model_b_path.read_bytes()
            with patch.object(run_storage, "_write_json_atomically", wraps=run_storage._write_json_atomically) as writer:
                upsert_result(run, self._result("모델 A"), path=index)
            self.assertEqual(
                [model_results_path(index, "모델 A"), index],
                [call.args[0] for call in writer.call_args_list],
            )
            self.assertEqual(model_b_before, model_b_path.read_bytes())
            self.assertEqual(1, len(load_run(index)["results"]))

    def test_verified_only_completion_and_invalidation_follow_input_mode(self) -> None:
        """@description raw 없는 verified 완료 판정과 재생성 무효화 확인"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            index = Path(temporary_directory) / "default" / "results.json"
            run = self._run("모델", input_mode="question")
            save_run(run, index)
            verified = {
                "exam_id": "example-text",
                "mode": "default",
                "model_name": "모델",
                "results": [
                    {"target": "국어/예시", "model_name": "모델", "question_number": 1, "complete": True},
                    {"target": "국어/예시", "model_name": "모델", "question_number": 2, "complete": True},
                ],
            }
            verified_path = model_verified_path(index, "모델")
            verified_path.write_text(json.dumps(verified, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(
                verified_result_is_completed(index, "모델", "국어/예시", 1, input_mode="question")
            )
            self.assertFalse(
                verified_result_is_completed(index, "모델", "국어/예시", 3, input_mode="question")
            )
            self.assertTrue(invalidate_verified_results(index, "모델", "국어/예시", 1, input_mode="question"))
            remaining = json.loads(verified_path.read_text(encoding="utf-8"))["results"]
            self.assertEqual([2], [row["question_number"] for row in remaining])

            section_run = self._run("모델", input_mode="section")
            save_run(section_run, index)
            verified["mode"] = "default"
            verified["results"] = [
                {"target": "국어/예시", "model_name": "모델", "question_number": 1, "complete": True},
                {"target": "국어/예시", "model_name": "모델", "question_number": 2, "complete": True},
            ]
            verified_path.write_text(json.dumps(verified, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(
                verified_result_is_completed(
                    index, "모델", "국어/예시", 0, input_mode="section", question_numbers=[1, 2]
                )
            )
            invalidate_verified_results(
                index, "모델", "국어/예시", 0, input_mode="section", question_numbers=[1, 2]
            )
            self.assertEqual([], json.loads(verified_path.read_text(encoding="utf-8"))["results"])

    def test_old_execution_id_document_is_not_loaded(self) -> None:
        """@description 구형 실행 ID 문서 미읽기 확인"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "results.json"
            path.write_text(json.dumps({"schema_version": 2, "run_id": "old"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_run(path)


if __name__ == "__main__":
    unittest.main()
