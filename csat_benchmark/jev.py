"""@description Jev 결정 API 요청·응답 처리"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping, Sequence
from io import BytesIO
from typing import Any

import requests
from PIL import Image

from .grading.extractor import AnswerVerifier
from .models import APIResponse, ModelConfig, Question
from .providers.base import APIClient
from .providers.requests import build_chat_content, validate_question_media


DEFAULT_JEV_URL = "https://openrouter.ai/api/alpha/decisions"


def _to_lossless_webp_data_url(data_url: str) -> str:
    """@description 이미지 data URL을 픽셀 보존 WebP로 변환"""
    image_bytes = base64.b64decode(data_url.partition(",")[2])
    output = BytesIO()
    with Image.open(BytesIO(image_bytes)) as image:
        image.convert("RGBA").save(
            output,
            format="WEBP",
            lossless=True,
            quality=100,
            method=6,
            exact=True,
        )
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/webp;base64,{encoded}"


def build_jev_questions(
    subject: str,
    questions: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """@description Jev 문항 ID·응답 기준 생성"""
    jev_questions: dict[str, dict[str, Any]] = {}
    seen_numbers: set[int] = set()

    for question_info in questions:
        number = question_info["number"]
        question_text = question_info["question_text"]
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError("Jev 문항 번호는 양의 정수여야 합니다.")
        if number in seen_numbers:
            raise ValueError(f"Jev 문항 번호가 중복되었습니다: {number}")
        if not isinstance(question_text, str):
            raise ValueError(f"Jev 문항 {number}의 question_text는 문자열이어야 합니다.")
        seen_numbers.add(number)

        question_id = f"q{number}"
        has_choice_context = bool(AnswerVerifier._extract_choice_context(question_text))
        if subject == "수학" and not has_choice_context:
            criteria = {str(digit): str(digit) for digit in range(10)}
            for place, place_name in (
                ("hundreds", "백의 자리"),
                ("tens", "십의 자리"),
                ("units", "일의 자리"),
            ):
                jev_questions[f"{question_id}_{place}"] = {
                    "type": "choice",
                    "instructions": (
                        f"시험지 {number}번 문항의 정답을 세 자리 숫자로 나타낼 때 "
                        f"{place_name}를 고르세요. 한 자리·두 자리 정답은 왼쪽을 0으로 채우세요."
                    ),
                    "criteria": criteria,
                }
        else:
            jev_questions[question_id] = {
                "type": "choice",
                "instructions": f"시험지 {number}번 문항의 정답 선택지를 고르세요.",
                "criteria": {str(choice): f"{choice}번 선택지" for choice in range(1, 6)},
            }

    return jev_questions


def decode_jev_answer(answers: Mapping[str, Any], number: int) -> int:
    """@description Jev 객관식 또는 세 자리 답안 디코드"""
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("Jev 문항 번호는 양의 정수여야 합니다.")

    question_id = f"q{number}"
    digit_places = ("hundreds", "tens", "units")
    digit_ids = [f"{question_id}_{place}" for place in digit_places]
    allowed_ids = {question_id, *digit_ids}
    question_answer_ids = {
        answer_id
        for answer_id in answers
        if answer_id == question_id or answer_id.startswith(f"{question_id}_")
    }
    if question_answer_ids - allowed_ids:
        raise ValueError(f"Jev 문항 {number}의 응답 필드가 잘못되었습니다.")
    has_choice = question_id in answers
    present_digit_ids = [answer_id for answer_id in digit_ids if answer_id in answers]

    if has_choice and present_digit_ids:
        raise ValueError(f"Jev 문항 {number}에 객관식·자리별 응답이 함께 있습니다.")
    if has_choice:
        entry = answers[question_id]
        if not isinstance(entry, Mapping) or entry.get("type") != "choice":
            raise ValueError(f"Jev 문항 {number}의 응답 형식이 잘못되었습니다.")
        choice = entry.get("choice")
        if not isinstance(choice, str) or choice not in {"1", "2", "3", "4", "5"}:
            raise ValueError(f"Jev 문항 {number}의 객관식 선택 값이 잘못되었습니다.")
        return int(choice)

    if len(present_digit_ids) != len(digit_ids):
        raise ValueError(f"Jev 문항 {number}의 응답이 없거나 자리별 응답이 불완전합니다.")

    digits: list[str] = []
    for answer_id in digit_ids:
        entry = answers[answer_id]
        if not isinstance(entry, Mapping) or entry.get("type") != "choice":
            raise ValueError(f"Jev 문항 {number}의 자리별 응답 형식이 잘못되었습니다.")
        digit = entry.get("choice")
        if not isinstance(digit, str) or digit not in {str(value) for value in range(10)}:
            raise ValueError(f"Jev 문항 {number}의 자리별 선택 값이 잘못되었습니다.")
        digits.append(digit)
    return int("".join(digits))


class JevClient(APIClient):
    """@description Jev 결정 API 클라이언트"""

    def __init__(self, config: ModelConfig, system_prompt: str | None = None):
        super().__init__(config)
        self.system_prompt = system_prompt
        self.api_url = config.base_url if config.base_url is not None else DEFAULT_JEV_URL

    def _failure_response(
        self,
        question: Question,
        error_message: str,
        failure_type: str,
        raw_response: str = "",
    ) -> APIResponse:
        """@description Jev 요청 기술 실패 응답 생성"""
        return APIResponse(
            question_number=question.number,
            model_name=self.config.name,
            raw_response=raw_response,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            success=False,
            error_message=error_message,
            answer_status="technical_failure",
            error_details={"failure_type": failure_type},
        )

    def send_questions(
        self,
        question: Question,
        *,
        subject: str,
        questions: Sequence[Mapping[str, Any]],
    ) -> APIResponse:
        """@description 준비된 문항 본문과 Jev 답안 기준 전송"""
        validate_question_media(question, self.config)
        jev_questions = build_jev_questions(subject, questions)
        question_text = question.load_question_text()
        state: str | list[dict[str, Any]] = question_text
        if self.config.supports_vision and question.image_paths:
            state = build_chat_content(
                question,
                supports_vision=True,
                skip_missing=False,
            )
            if question_text:
                state.insert(0, state.pop())
            for part in state:
                if part["type"] == "image_url":
                    part["image_url"]["url"] = _to_lossless_webp_data_url(
                        part["image_url"]["url"]
                    )
                    part["image_url"]["detail"] = "high"
        payload = {
            "model": self.config.model_id,
            "state": state,
            "questions": jev_questions,
        }
        if self.system_prompt:
            for jev_question in jev_questions.values():
                jev_question["instructions"] += f"\n\n{self.system_prompt}"

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self._get_next_api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(30, 6000),
            )
        except requests.RequestException as exc:
            return self._failure_response(
                question,
                f"Jev API 요청 중 네트워크 오류: {exc}",
                "network_error",
            )

        if response.status_code < 200 or response.status_code >= 300:
            return self._failure_response(
                question,
                f"Jev API에서 HTTP {response.status_code} 응답: {response.text}",
                "http_error",
                response.text,
            )

        try:
            response_data = response.json()
        except ValueError as exc:
            return self._failure_response(
                question,
                f"Jev API 응답이 JSON 형식이 아닙니다: {exc}",
                "invalid_json",
                response.text,
            )

        raw_response = json.dumps(response_data, ensure_ascii=False)
        if not isinstance(response_data, Mapping):
            return self._failure_response(
                question,
                "Jev API 응답은 JSON 객체여야 합니다.",
                "invalid_response",
                raw_response,
            )

        answers = response_data.get("answers")
        expected_ids = set(jev_questions)
        if not isinstance(answers, Mapping) or set(answers) != expected_ids:
            return self._failure_response(
                question,
                "Jev API 응답 문항 ID가 요청과 일치하지 않습니다.",
                "invalid_answers",
                raw_response,
            )

        try:
            for question_info in questions:
                decode_jev_answer(answers, question_info["number"])
        except ValueError as exc:
            return self._failure_response(
                question,
                f"Jev API 답안이 유효하지 않습니다: {exc}",
                "invalid_answers",
                raw_response,
            )

        usage = response_data.get("usage")
        if not isinstance(usage, Mapping):
            return self._failure_response(
                question,
                "Jev API 사용량 정보 형식이 잘못되었습니다.",
                "invalid_usage",
                raw_response,
            )
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if any(
            isinstance(token_count, bool)
            or not isinstance(token_count, int)
            or token_count < 0
            for token_count in (input_tokens, output_tokens)
        ):
            return self._failure_response(
                question,
                "Jev API 토큰 사용량은 0 이상의 정수여야 합니다.",
                "invalid_usage",
                raw_response,
            )
        total_tokens = input_tokens + output_tokens

        return APIResponse(
            question_number=question.number,
            model_name=self.config.name,
            raw_response=raw_response,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            success=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            answer_status="answered",
        )
