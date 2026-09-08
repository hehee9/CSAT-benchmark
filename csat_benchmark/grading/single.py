"""@description 단일 생성 결과의 답안 추출·과목·섹션 채점 정책"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .extractor import AnswerVerifier


@dataclass
class VerificationResult:
    """@description 단일 생성 결과의 답안 추출·정답 판정 결과"""

    question_number: int
    model_name: str
    raw_response: str
    extracted_answer: Optional[int]
    correct_answer: int
    is_correct: bool
    points: int
    needs_manual_review: bool = False
    answer_status: str = "answered"
    provider_stop_reason: Optional[str] = None


def _load_question_text(question_path: str, base_dir: Path) -> Optional[str]:
    """@description 채점 입력용 문제 본문 로드"""
    full_path = base_dir / question_path
    if not full_path.exists():
        return None
    try:
        with full_path.open("r", encoding="utf-8") as file:
            return file.read().strip()
    except OSError as error:
        print(f"  ⚠ 문제 파일 읽기 오류: {error}")
        return None


def verify_single_result(
    verifier: AnswerVerifier,
    result: Dict[str, Any],
    question_info: Dict[str, Any],
    idx: int,
    base_dir: Path,
) -> tuple[VerificationResult, Optional[tuple]]:
    """@description 일반 모드 단일 생성 결과를 두 차례 추출하고 필요 시 재확인"""
    del idx
    question_num = result.get("question_number")
    model_name = result.get("model_name")
    raw_response = result.get("raw_response", "")
    answer_status = result.get("answer_status")
    provider_stop_reason = result.get("provider_stop_reason")
    correct_answer = question_info["correct_answer"]
    points = question_info["points"]
    question_path = question_info.get("question_path", "")

    if answer_status == "refusal" or provider_stop_reason == "refusal":
        return VerificationResult(
            question_number=question_num,
            model_name=model_name,
            raw_response=raw_response,
            extracted_answer=-2,
            correct_answer=correct_answer,
            is_correct=False,
            points=points,
            needs_manual_review=False,
            answer_status="refusal",
            provider_stop_reason=provider_stop_reason,
        ), None

    question_text = question_info.get("question_text")
    if question_text is None and question_path:
        question_text = _load_question_text(question_path, base_dir)

    attempt1 = verifier.verify_answer(raw_response, correct_answer, question_num, question_text)
    attempt2 = verifier.verify_answer(raw_response, correct_answer, question_num, question_text)

    needs_review = False
    final_answer = None
    manual_review_data = None

    # 기존 검증기의 계약을 보존한다. None·불일치도 3차 확인 대상으로 취급한다.
    if attempt1 is not None and attempt2 is not None and attempt1 == attempt2:
        final_answer = attempt1
    else:
        attempt3 = verifier.verify_answer(raw_response, correct_answer, question_num, question_text)
        if attempt1 is not None and attempt1 == attempt3:
            final_answer = attempt1
        elif attempt2 is not None and attempt2 == attempt3:
            final_answer = attempt2
        else:
            candidates = [answer for answer in (attempt1, attempt2, attempt3) if answer is not None]
            if candidates:
                needs_review = True
                final_answer = candidates[0]
                manual_review_data = (model_name, question_num, [attempt1, attempt2, attempt3])

    is_correct = (final_answer == correct_answer) if final_answer is not None else False
    if final_answer is None:
        answer_status = "parse_failed"
    elif final_answer == -1:
        answer_status = "no_answer"
    else:
        answer_status = "answered"

    return VerificationResult(
        question_number=question_num,
        model_name=model_name,
        raw_response=raw_response,
        extracted_answer=final_answer,
        correct_answer=correct_answer,
        is_correct=is_correct,
        points=points,
        needs_manual_review=needs_review,
        answer_status=answer_status,
        provider_stop_reason=provider_stop_reason,
    ), manual_review_data


def _normalize_hard_answer_map(
    answers: Optional[List[Dict[str, int]]],
) -> Optional[Dict[int, Dict[str, int]]]:
    """@description hard 추출 결과 배열을 문항 번호별 매핑으로 변환"""
    if answers is None:
        return None

    answer_map: Dict[int, Dict[str, int]] = {}
    for answer in answers:
        try:
            question_number = int(answer["question_number"])
            answer_map[question_number] = {
                "correct_answer": int(answer["correct_answer"]),
                "llm_answer": int(answer["llm_answer"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return answer_map


def _hard_answer_value(
    answer_map: Optional[Dict[int, Dict[str, int]]], question_number: int
) -> Optional[int]:
    """@description hard 추출 매핑에서 특정 문항 답 조회"""
    if answer_map is None:
        return None
    answer = answer_map.get(question_number)
    if answer is None:
        return None
    return answer.get("llm_answer")


def _has_correct_answer_mismatch(
    answer_maps: List[Optional[Dict[int, Dict[str, int]]]],
    question_number: int,
    correct_answer: int,
) -> bool:
    """@description hard 추출 결과의 정답 필드 불일치 여부 확인"""
    for answer_map in answer_maps:
        if answer_map is None or question_number not in answer_map:
            continue
        if answer_map[question_number].get("correct_answer") != correct_answer:
            return True
    return False


def verify_hard_single_result(
    verifier: AnswerVerifier,
    result: Dict[str, Any],
    question_infos: List[Dict[str, Any]],
    idx: int,
) -> tuple[List[VerificationResult], List[tuple]]:
    """@description 섹션 모드 단일 생성 결과를 문항별로 검증"""
    del idx
    model_name = result.get("model_name")
    raw_response = result.get("raw_response", "")
    answer_status = result.get("answer_status")
    provider_stop_reason = result.get("provider_stop_reason")

    if answer_status == "refusal" or provider_stop_reason == "refusal":
        return [
            VerificationResult(
                question_number=question_info["number"],
                model_name=model_name,
                raw_response=raw_response,
                extracted_answer=-2,
                correct_answer=question_info["correct_answer"],
                is_correct=False,
                points=question_info["points"],
                needs_manual_review=False,
                answer_status="refusal",
                provider_stop_reason=provider_stop_reason,
            )
            for question_info in question_infos
        ], []

    if not result.get("success", False) or not raw_response:
        return [
            VerificationResult(
                question_number=question_info["number"],
                model_name=model_name,
                raw_response=raw_response,
                extracted_answer=None,
                correct_answer=question_info["correct_answer"],
                is_correct=False,
                points=question_info["points"],
                needs_manual_review=False,
                answer_status="parse_failed",
                provider_stop_reason=provider_stop_reason,
            )
            for question_info in question_infos
        ], []

    attempt1 = _normalize_hard_answer_map(verifier.verify_hard_answers(raw_response, question_infos))
    attempt2 = _normalize_hard_answer_map(verifier.verify_hard_answers(raw_response, question_infos))

    retry_questions = []
    final_answers: Dict[int, int] = {}
    needs_review_by_question: Dict[int, bool] = {}
    manual_review_needed = []

    for question_info in question_infos:
        question_number = question_info["number"]
        answer1 = _hard_answer_value(attempt1, question_number)
        answer2 = _hard_answer_value(attempt2, question_number)
        if answer1 is not None and answer2 is not None and answer1 == answer2:
            final_answers[question_number] = answer1
        else:
            retry_questions.append(question_info)

    attempt3 = None
    if retry_questions:
        attempt3 = _normalize_hard_answer_map(
            verifier.verify_hard_answers(raw_response, retry_questions)
        )

    for question_info in retry_questions:
        question_number = question_info["number"]
        answer1 = _hard_answer_value(attempt1, question_number)
        answer2 = _hard_answer_value(attempt2, question_number)
        answer3 = _hard_answer_value(attempt3, question_number)

        if answer1 is not None and answer1 == answer3:
            final_answers[question_number] = answer1
        elif answer2 is not None and answer2 == answer3:
            final_answers[question_number] = answer2
        else:
            candidate_answers = [answer for answer in [answer1, answer2, answer3] if answer is not None]
            if candidate_answers:
                final_answers[question_number] = candidate_answers[0]
                needs_review_by_question[question_number] = True
                manual_review_needed.append((model_name, question_number, [answer1, answer2, answer3]))
            else:
                final_answers[question_number] = -1

    if attempt1 is None and attempt2 is None and attempt3 is None:
        return [
            VerificationResult(
                question_number=question_info["number"],
                model_name=model_name,
                raw_response=raw_response,
                extracted_answer=None,
                correct_answer=question_info["correct_answer"],
                is_correct=False,
                points=question_info["points"],
                needs_manual_review=False,
                answer_status="parse_failed",
                provider_stop_reason=provider_stop_reason,
            )
            for question_info in question_infos
        ], []

    verification_results = []
    all_attempts = [attempt1, attempt2, attempt3]
    for question_info in question_infos:
        question_number = question_info["number"]
        correct_answer = question_info["correct_answer"]
        final_answer = final_answers.get(question_number)
        needs_review = needs_review_by_question.get(question_number, False)

        if _has_correct_answer_mismatch(all_attempts, question_number, correct_answer):
            needs_review = True
            manual_review_needed.append((model_name, question_number, ["correct_answer_mismatch"]))

        if final_answer is None:
            answer_status = "parse_failed"
            is_correct = False
        elif final_answer == -1:
            answer_status = "no_answer"
            is_correct = False
        else:
            answer_status = "answered"
            is_correct = final_answer == correct_answer

        verification_results.append(
            VerificationResult(
                question_number=question_number,
                model_name=model_name,
                raw_response=raw_response,
                extracted_answer=final_answer,
                correct_answer=correct_answer,
                is_correct=is_correct,
                points=question_info["points"],
                needs_manual_review=needs_review,
                answer_status=answer_status,
                provider_stop_reason=provider_stop_reason,
            )
        )

    return verification_results, manual_review_needed


__all__ = [
    "VerificationResult",
    "_hard_answer_value",
    "_has_correct_answer_mismatch",
    "_normalize_hard_answer_map",
    "verify_hard_single_result",
    "verify_single_result",
]
