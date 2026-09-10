"""@description 정답 값 검증과 추출 답안의 정답 여부 판정"""

from __future__ import annotations

from typing import TypeAlias


CorrectAnswer: TypeAlias = int | list[int]


def _validate_correct_answer(value: object) -> CorrectAnswer:
    """@description 정답 값 형식 검증 및 원본 값 반환"""
    if isinstance(value, bool):
        raise ValueError("정답은 boolean일 수 없습니다.")
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        if not value:
            raise ValueError("복수 정답 목록은 비어 있을 수 없습니다.")
        if any(
            isinstance(answer, bool) or not isinstance(answer, int) or answer < 0
            for answer in value
        ):
            raise ValueError("복수 정답 목록은 음이 아닌 정수만 포함해야 합니다.")
        return value
    raise ValueError("정답은 정수 또는 정수 목록이어야 합니다.")


def _is_correct_answer(answer: object, correct_answer: CorrectAnswer) -> bool:
    """@description 추출 답안의 정답 포함 여부 판정"""
    if answer is None or isinstance(answer, bool) or not isinstance(answer, int) or answer < 0:
        return False
    if isinstance(correct_answer, list):
        return answer in correct_answer
    return answer == correct_answer


__all__ = ["CorrectAnswer", "_is_correct_answer", "_validate_correct_answer"]
