"""@description Batch 결과 파싱 공용 변환 함수"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...models import EMPTY_RESPONSE_ERROR, _has_response_or_token_usage


def extract_question_number(request_id: Optional[str]) -> Optional[int]:
    """@description 요청 ID 기반 문항 번호 추출"""
    if not request_id:
        return None
    match = re.search(r"(\d+)$", request_id)
    if not match:
        return None
    return int(match.group(1))


def flatten_text(value: Any) -> str:
    """@description 중첩 응답 텍스트 병합"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("output_text"), str):
            return value["output_text"]
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        if isinstance(value.get("message"), str):
            return value["message"]
        if isinstance(value.get("refusal"), str):
            return value["refusal"]
        if "choices" in value:
            return flatten_text(value["choices"])
        if isinstance(value.get("delta"), dict):
            return flatten_text(value["delta"])
        if "content" in value:
            return flatten_text(value["content"])
        if "message" in value:
            return flatten_text(value["message"])
        if "response" in value:
            return flatten_text(value["response"])
    return ""


def contains_refusal(value: Any) -> bool:
    """@description 중첩 응답 거부 콘텐츠 포함 여부 확인"""
    if isinstance(value, dict):
        if isinstance(value.get("refusal"), str):
            return True
        return any(
            contains_refusal(child)
            for key in ("output", "content", "choices", "message")
            if key in value
            for child in (value[key],)
        )
    if isinstance(value, list):
        return any(contains_refusal(item) for item in value)
    return False


def flatten_anthropic_content(content: Any) -> str:
    """@description Anthropic 텍스트 블록 병합"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    text_parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "".join(text_parts)


def extract_usage_fields(usage: Any) -> Dict[str, Optional[int]]:
    """@description OpenAI 호환·Anthropic usage 필드 공용 이름 변환"""
    if not isinstance(usage, dict):
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

    input_tokens = usage.get("input_tokens")
    if not isinstance(input_tokens, int) or isinstance(input_tokens, bool):
        input_tokens = usage.get("prompt_tokens")
    if not isinstance(input_tokens, int) or isinstance(input_tokens, bool):
        input_tokens = None

    output_tokens = usage.get("output_tokens")
    if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
        output_tokens = usage.get("completion_tokens")
    if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
        output_tokens = None

    total_tokens = usage.get("total_tokens")
    if not isinstance(total_tokens, int) or isinstance(total_tokens, bool):
        total_tokens = None
    reasoning_tokens = None
    for details_key in ("completion_tokens_details", "output_tokens_details"):
        details = usage.get(details_key)
        if isinstance(details, dict):
            candidate = details.get("reasoning_tokens")
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                reasoning_tokens = candidate
                break
    if reasoning_tokens is None:
        candidate = usage.get("reasoning_tokens")
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            reasoning_tokens = candidate

    if isinstance(input_tokens, int) and isinstance(total_tokens, int):
        derived_output_tokens = total_tokens - input_tokens
        if derived_output_tokens >= 0:
            output_tokens = derived_output_tokens
    elif isinstance(output_tokens, int) and isinstance(reasoning_tokens, int):
        output_tokens += reasoning_tokens
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) else None,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else None,
        "total_tokens": total_tokens,
    }


def extract_google_usage_fields(usage: Any) -> Dict[str, Optional[int]]:
    """@description Gemini usageMetadata 토큰 사용량 추출"""
    if not isinstance(usage, dict):
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }

    input_tokens = usage.get("promptTokenCount")
    output_tokens = usage.get("candidatesTokenCount")
    thoughts_tokens = usage.get("thoughtsTokenCount")
    total_tokens = usage.get("totalTokenCount")

    if isinstance(output_tokens, int):
        if isinstance(thoughts_tokens, int):
            output_tokens += thoughts_tokens
    elif isinstance(thoughts_tokens, int):
        output_tokens = thoughts_tokens
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) else None,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else None,
        "total_tokens": total_tokens if isinstance(total_tokens, int) else None,
    }


def load_json_objects(result_path: Path) -> List[dict]:
    """@description 줄바꿈 무관 연속 JSON 객체 로드"""
    text = result_path.read_text(encoding="utf-8")
    if not text.strip():
        return []

    decoder = json.JSONDecoder()
    objects: List[dict] = []
    index = 0
    text_length = len(text)

    while index < text_length:
        while index < text_length and text[index].isspace():
            index += 1

        if index >= text_length:
            break

        obj, next_index = decoder.raw_decode(text, index)
        if isinstance(obj, dict):
            objects.append(obj)
        index = next_index

    return objects


def extract_anthropic_error_message(result_data: dict) -> str:
    """@description Anthropic 오류 객체 표시 메시지 추출"""
    error = result_data.get("error", {})
    if isinstance(error, dict):
        nested_error = error.get("error", {})
        if isinstance(nested_error, dict):
            message = nested_error.get("message")
            if isinstance(message, str) and message:
                return message

        message = error.get("message")
        if isinstance(message, str) and message:
            return message

        return json.dumps(error, ensure_ascii=False)

    if isinstance(error, str) and error:
        return error

    return "Unknown error"


__all__ = [
    "EMPTY_RESPONSE_ERROR",
    "_has_response_or_token_usage",
    "contains_refusal",
    "extract_anthropic_error_message",
    "extract_google_usage_fields",
    "extract_question_number",
    "extract_usage_fields",
    "flatten_anthropic_content",
    "flatten_text",
    "load_json_objects",
]
