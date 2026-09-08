from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import sync_data
from csat_benchmark.configuration import load_config
from csat_benchmark.exams import load_exam
from csat_benchmark.exports import publish_run
from csat_benchmark.metadata import sync_model_metadata
from csat_benchmark.models import APIResponse, ModelConfig
from csat_benchmark.runner import run_exam
from csat_benchmark.runs import create_run


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_config_adds_null_cutoff_without_resolving_credentials(tmp_path: Path) -> None:
    """설정의 지식 컷오프 기본값과 인증 정보 비해석 경로 검증."""
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "models": [
                {
                    "name": "모델",
                    "api_type": "openai",
                    "api_key_env": "MISSING_METADATA_KEY",
                    "model_id": "mock",
                }
            ]
        },
    )
    config = load_config(config_path, resolve_secrets=False)
    assert config["models"][0]["knowledge_cutoff"] is None
    assert "api_key" not in config["models"][0]


@pytest.mark.parametrize("value", ["", "2026", "2026-00", "2026-13", 202601])
def test_invalid_knowledge_cutoff_is_rejected(tmp_path: Path, value: object) -> None:
    """잘못된 지식 컷오프 형식의 설정 로드 거부 검증."""
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "models": [
                {
                    "name": "모델",
                    "api_type": "openai",
                    "model_id": "mock",
                    "knowledge_cutoff": value,
                }
            ]
        },
    )
    with pytest.raises(ValueError, match="knowledge_cutoff"):
        load_config(config_path, resolve_secrets=False)


def test_model_config_accepts_null_and_rejects_invalid_cutoff() -> None:
    """공용 모델 자료 클래스의 컷오프 검증."""
    assert ModelConfig("모델", "openai", "key", "mock").knowledge_cutoff is None
    with pytest.raises(ValueError, match="knowledge_cutoff"):
        ModelConfig("모델", "openai", "key", "mock", knowledge_cutoff="2026-13")


@pytest.mark.parametrize("value", ["", "2026", "2026-00", "2026-13", 202609])
def test_invalid_exam_month_is_rejected(tmp_path: Path, value: object) -> None:
    """잘못된 시험 시행 월 형식의 매니페스트 로드 거부 검증."""
    manifest_path = tmp_path / "exam.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "id": "exam",
            "title": "시험",
            "data_dir": "data",
            "results_dir": "results",
            "exam_month": value,
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
            "modes": [{"id": "default", "label": "기본", "input_mode": "section", "attempts": 1}],
        },
    )
    with pytest.raises(ValueError, match="exam_month"):
        load_exam(manifest_path, project_root=tmp_path)


def test_missing_exam_metadata_uses_legacy_defaults(tmp_path: Path) -> None:
    """기존 사용자 매니페스트의 시험 메타데이터 기본값 검증."""
    manifest_path = tmp_path / "exam.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "id": "exam",
            "title": "기존 시험",
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
            "modes": [{"id": "default", "label": "기본", "input_mode": "section", "attempts": 1}],
        },
    )
    exam = load_exam(manifest_path, project_root=tmp_path)
    assert exam.short_name == exam.title
    assert exam.exam_month is None


def test_metadata_sync_preserves_existing_descriptions_flags_and_models(tmp_path: Path) -> None:
    """선택 모델 필드만 갱신하고 기존 공개 메타데이터를 보존한다."""
    metadata_path = tmp_path / "web" / "model_metadata.json"
    metadata_path.parent.mkdir()
    metadata_path.write_text(
        json.dumps(
            {
                "기존 모델": {
                    "description": {"ko": "설명"},
                    "webServiceNoTools": True,
                    "supportsVision": True,
                },
                "보존 모델": {"description": {"ko": "그대로"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert sync_model_metadata(
        {
            "기존 모델": {
                "name": "기존 모델",
                "supports_vision": False,
                "knowledge_cutoff": "2025-11",
            },
            "새 모델": {"name": "새 모델", "knowledge_cutoff": None},
        },
        metadata_path,
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["기존 모델"] == {
        "description": {"ko": "설명"},
        "webServiceNoTools": True,
        "supportsVision": False,
        "knowledgeCutoff": "2025-11",
    }
    assert metadata["보존 모델"] == {"description": {"ko": "그대로"}}
    assert metadata["새 모델"]["knowledgeCutoff"] is None


def test_metadata_cli_is_credential_free_and_does_not_construct_sync_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """metadata 명령이 Excel 없이 설정과 출력 파일만 처리한다."""
    config_path = tmp_path / "config.json"
    output_path = tmp_path / "metadata.json"
    _write_json(
        config_path,
        {
            "models": [
                {
                    "name": "모델",
                    "api_type": "openai",
                    "api_key_env": "MISSING_METADATA_KEY",
                    "model_id": "mock",
                    "knowledge_cutoff": "2025-11",
                }
            ]
        },
    )
    monkeypatch.setattr(sync_data, "SyncManager", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Excel 로드 금지")))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_data.py",
            "metadata",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )
    monkeypatch.delenv("MISSING_METADATA_KEY", raising=False)
    assert sync_data.main() == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["모델"]["knowledgeCutoff"] == "2025-11"


class _FixedClient:
    """재개 호환성 확인용 유료 호출 없는 공급자 대역."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def send_request(self, question):
        return APIResponse(
            question_number=question.number,
            model_name=self.config.name,
            raw_response="응답",
            timestamp="2026-09-07T00:00:00+00:00",
            success=True,
        )


def test_cutoff_only_change_keeps_immediate_run_compatible(tmp_path: Path) -> None:
    """지식 컷오프만 바꾼 설정으로 기존 실행을 재개한다."""
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "models": [
                {
                    "name": "모델",
                    "api_type": "openai",
                    "api_key_env": "RUN_METADATA_KEY",
                    "model_id": "mock",
                    "knowledge_cutoff": "2025-11",
                    "batch_supported": False,
                    "concurrent_request_limit": 1,
                }
            ]
        },
    )
    exam = load_exam("example-text")
    output_path = tmp_path / "run" / "results.json"
    with patch.dict(os.environ, {"RUN_METADATA_KEY": "test-key"}):
        first = run_exam(
            exam,
            config_path=config_path,
            output=output_path,
            client_factory=lambda config, *, system_prompt: _FixedClient(config),
        )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["models"][0]["knowledge_cutoff"] = "2026-01"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        resumed = run_exam(
            exam,
            config_path=config_path,
            run_id=first["run_id"],
            output=output_path,
            client_factory=lambda config, *, system_prompt: _FixedClient(config),
        )
    assert resumed["run_id"] == first["run_id"]
    assert resumed["selected_models"][0]["knowledge_cutoff"] == "2025-11"


def test_modern_publish_uses_override_metadata_and_manifest_destination(tmp_path: Path) -> None:
    """공개 시 선택 모델 메타데이터와 현재 설정 재정의를 통합한다."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "questions.json").write_text(
        json.dumps(
            {
                "subject": "국어",
                "section": "예시",
                "questions": [
                    {"number": 1, "correct_answer": 2, "points": 2, "question_path": "1.txt"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "data" / "1.txt").write_text("예시 문항", encoding="utf-8")
    manifest_path = tmp_path / "benchmarks" / "local.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "id": "local",
            "title": "로컬 시험",
            "short_name": "로컬",
            "exam_month": "2026-09",
            "data_dir": "data",
            "results_dir": "results",
            "publish": True,
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
            "modes": [{"id": "default", "label": "기본", "input_mode": "section", "attempts": 1}],
        },
    )
    exam = load_exam(manifest_path, project_root=tmp_path)
    run = create_run(
        exam_id="local",
        mode="default",
        input_mode="section",
        attempts_expected=1,
        selected_targets=["국어/예시"],
        selected_models=[
            {
                "name": "모델",
                "supports_vision": False,
                "knowledge_cutoff": "2025-11",
            }
        ],
        input_context=[{"target": "국어/예시", "question_numbers": [1]}],
    )
    run["results"].append(
        {
            "target": "국어/예시",
            "subject": "국어",
            "section": "예시",
            "model_name": "모델",
            "attempt": 1,
            "question_number": 0,
            "raw_response": "응답",
            "timestamp": "2026-09-07T00:00:00+00:00",
            "success": True,
            "error_message": None,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "answer_status": None,
            "provider_stop_reason": None,
            "error_details": None,
        }
    )
    verified = {
        "run_id": run["run_id"],
        "selected_models": ["모델"],
        "results": [
            {
                "target": "국어/예시",
                "subject": "국어",
                "section": "예시",
                "model_name": "모델",
                "question_number": 1,
                "correct_answer": 2,
                "points": 2,
                "complete": True,
                "needs_manual_review": False,
                "is_correct": True,
                "extracted_answer": 2,
                "attempts": [],
            }
        ],
    }
    existing_path = tmp_path / "web" / "model_metadata.json"
    _write_json(existing_path, {"모델": {"description": {"ko": "기존"}, "webServiceNoTools": True}})
    override_path = tmp_path / "override.json"
    _write_json(
        override_path,
        {
            "models": [
                {
                    "name": "모델",
                    "api_type": "openai",
                    "model_id": "mock",
                    "api_key_env": "MISSING_METADATA_KEY",
                    "supports_vision": True,
                    "knowledge_cutoff": "2026-02",
                }
            ]
        },
    )
    paths = publish_run(
        exam,
        run,
        verified,
        output_dir=tmp_path / "published",
        config_path=override_path,
    )
    assert paths["model_metadata"] == existing_path.resolve()
    metadata = json.loads(existing_path.read_text(encoding="utf-8"))
    assert metadata["모델"] == {
        "description": {"ko": "기존"},
        "webServiceNoTools": True,
        "knowledgeCutoff": "2026-02",
    }
