"""@description 저장된 Jev 답안을 결정적으로 채점"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .answers import _is_correct_answer
from .evaluation import EvaluationError
from .grading.single import VerificationResult
from .jev import decode_jev_answer


def _load_jev_answers(result: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    """@description 성공한 원본 Jev 응답의 answers 객체를 한 번 파싱"""
    raw_response = result.get("raw_response")
    if not isinstance(raw_response, str):
        raise EvaluationError("Jev 저장 응답 raw_response는 문자열이어야 합니다.")
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise EvaluationError("성공한 Jev 저장 응답이 올바른 JSON이 아닙니다.") from error
    if not isinstance(payload, Mapping):
        raise EvaluationError("성공한 Jev 저장 응답은 JSON 객체여야 합니다.")
    answers = payload.get("answers")
    if not isinstance(answers, Mapping):
        raise EvaluationError("성공한 Jev 저장 응답에 answers 객체가 없습니다.")
    return raw_response, answers


def _verification_result(
    result: Mapping[str, Any],
    question_info: Mapping[str, Any],
    raw_response: str,
    answers: Mapping[str, Any],
) -> VerificationResult:
    """@description Jev 선택값을 기존 canonical 단일 채점 결과로 변환"""
    question_number = int(question_info["number"])
    try:
        answer = decode_jev_answer(answers, question_number)
    except ValueError as error:
        raise EvaluationError(
            f"성공한 Jev 저장 응답의 문제 {question_number}번 답안이 잘못되었습니다: {error}"
        ) from error
    correct_answer = question_info["correct_answer"]
    return VerificationResult(
        question_number=question_number,
        model_name=result["model_name"],
        raw_response=raw_response,
        extracted_answer=answer,
        correct_answer=correct_answer,
        is_correct=_is_correct_answer(answer, correct_answer),
        points=int(question_info["points"]),
        needs_manual_review=False,
        answer_status="answered",
        provider_stop_reason=result.get("provider_stop_reason"),
    )


def verify_jev_single_result(
    verifier: Any,
    result: dict[str, Any],
    question_info: dict[str, Any],
    idx: int,
    base_dir: Path,
) -> tuple[VerificationResult, None]:
    """@description 문항별 Jev 원본 응답을 한 번 읽어 답안 채점"""
    del verifier, idx, base_dir
    raw_response, answers = _load_jev_answers(result)
    return _verification_result(result, question_info, raw_response, answers), None


def verify_jev_section_result(
    verifier: Any,
    result: dict[str, Any],
    question_infos: list[dict[str, Any]],
    idx: int,
) -> tuple[list[VerificationResult], list[tuple[Any, ...]]]:
    """@description 섹션 Jev 원본 응답을 한 번 읽어 선택 문항만 채점"""
    del verifier, idx
    raw_response, answers = _load_jev_answers(result)
    return [
        _verification_result(result, question_info, raw_response, answers)
        for question_info in question_infos
    ], []


__all__ = ["verify_jev_section_result", "verify_jev_single_result"]
