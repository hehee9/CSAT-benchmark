"""@description Jev 전용 설정 검증 및 공용 실행기 연결"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .configuration import load_config
from .exams import ExamManifest
from .jev import JevClient
from .models import APIResponse
from .runner import ImmediateJob, RunnerError, check_exam, run_exam


def _validate_jev_models(
    config_path: str | Path,
    model_names: Sequence[str] | None,
) -> None:
    """@description 선택 모델의 Jev 전용 설정 검증"""
    config = load_config(
        config_path,
        model_names=model_names,
        resolve_secrets=False,
        resolve_verifier_secrets=False,
    )
    for model in config["models"]:
        name = model.get("name")
        if model.get("api_type") != "jev":
            raise RunnerError(f"{name}의 api_type은 jev여야 합니다.")


def check_jev_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    model_names: Sequence[str] | None = None,
    **options: Any,
) -> Dict[str, Any]:
    """@description Jev 모델·시험 입력 사전 검증"""
    _validate_jev_models(config_path, model_names)
    return check_exam(
        exam,
        config_path=config_path,
        model_names=model_names,
        **options,
    )


def _send_jev_request(
    client: JevClient,
    job: ImmediateJob,
    context: Mapping[str, Any],
) -> APIResponse:
    """@description 실행 단위별 원문 문항 정보 Jev 요청"""
    questions = context["questions"]
    if context["input_mode"] == "question":
        questions = [item for item in questions if item["number"] == job.question_number]
    question_metadata = [
        {"number": item["number"], "question_text": item["question_text"]}
        for item in questions
    ]
    return client.send_questions(
        job.question,
        subject=job.subject,
        questions=question_metadata,
    )


def run_jev_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    model_names: Sequence[str] | None = None,
    **options: Any,
) -> Dict[str, Any]:
    """@description Jev 요청으로 공용 실행기 수명 주기 수행"""
    _validate_jev_models(config_path, model_names)
    return run_exam(
        exam,
        config_path=config_path,
        model_names=model_names,
        client_factory=JevClient,
        request_sender=_send_jev_request,
        **options,
    )


__all__ = ["check_jev_exam", "run_jev_exam"]
