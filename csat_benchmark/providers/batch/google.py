"""@description Google Gemini Batch API 전송·결과 파싱"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import requests

from ...models import ModelConfig
from .common import (
    EMPTY_RESPONSE_ERROR,
    _has_response_or_token_usage,
    extract_google_usage_fields,
    extract_question_number,
)


try:
    from google import genai

    GOOGLE_GENAI_AVAILABLE = True
except (ImportError, AttributeError):
    GOOGLE_GENAI_AVAILABLE = False
    genai = None
    print("경고: google-genai 패키지가 설치되지 않았습니다. Gemini 배치는 실행: pip install google-genai")


GOOGLE_BATCH_POLL_SECONDS = 60
GOOGLE_TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
    "BATCH_STATE_SUCCEEDED",
    "BATCH_STATE_FAILED",
    "BATCH_STATE_CANCELLED",
    "BATCH_STATE_EXPIRED",
    "BATCH_STATE_PARTIALLY_SUCCEEDED",
}
GOOGLE_SUCCESS_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
    "BATCH_STATE_SUCCEEDED",
    "BATCH_STATE_PARTIALLY_SUCCEEDED",
}


def initialize_client(
    model_config: ModelConfig,
    resolve_api_key: Callable[[ModelConfig], str],
) -> Any:
    """@description Google GenAI SDK 클라이언트 초기화"""
    if not GOOGLE_GENAI_AVAILABLE:
        raise ImportError("google-genai 패키지가 설치되지 않았습니다. 실행: pip install google-genai")
    return genai.Client(api_key=resolve_api_key(model_config))


def batch_url(model_config: ModelConfig) -> str:
    """@description Gemini batchGenerateContent REST URL 생성"""
    model_id = model_config.model_id
    if not model_id.startswith("models/"):
        model_id = f"models/{model_id}"
    return (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"{model_id}:batchGenerateContent"
    )


def resource_url(resource_name: str) -> str:
    """@description Gemini Batch resource REST URL 생성"""
    return f"https://generativelanguage.googleapis.com/v1beta/{resource_name}"


def request(
    method: str,
    url: str,
    model_config: ModelConfig,
    resolve_api_key: Callable[[ModelConfig], str],
    json_body: Optional[dict] = None,
) -> dict:
    """@description Gemini Batch REST 요청 실행"""
    api_key = resolve_api_key(model_config)
    response = requests.request(
        method,
        url,
        params={"key": api_key},
        json=json_body,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"Gemini Batch API 요청 실패 ({response.status_code}) {method} {url}: {response.text}"
        )

    if not response.content:
        return {}

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Gemini Batch API 응답이 JSON이 아닙니다: {response.text}") from exc


def create_batch(
    model_config: ModelConfig,
    batch_requests: List[dict],
    display_name: str,
    request_fn: Callable[..., dict],
) -> dict:
    """@description Gemini Batch 작업 생성"""
    print(f"🚀 Gemini 배치 작업 생성 중... (displayName: {display_name})")
    payload = {
        "batch": {
            "displayName": display_name,
            "inputConfig": {
                "requests": {
                    "requests": batch_requests,
                }
            },
        }
    }
    batch = request_fn(
        "POST",
        batch_url(model_config),
        model_config,
        json_body=payload,
    )
    batch_id = batch.get("name")
    if not batch_id:
        raise RuntimeError(f"Gemini 배치 생성 응답에 name이 없습니다: {batch}")

    print(f"✅ Gemini 배치 작업 생성됨: {batch_id}")
    batch_metadata = batch.get("metadata") or {}
    print(f"   상태: {batch.get('state') or batch_metadata.get('state')}")
    return batch


def extract_inlined_responses(result_data: Dict[str, Any]) -> List[dict]:
    """@description Gemini 배치 인라인 응답 목록 추출"""
    destination = result_data.get("dest") or result_data.get("destination") or {}
    response_payload = result_data.get("response") or {}
    metadata = result_data.get("metadata") or {}
    metadata_output = metadata.get("output") or {}
    candidates = [
        destination.get("inlinedResponses"),
        destination.get("inlined_responses"),
        response_payload.get("inlinedResponses"),
        response_payload.get("inlined_responses"),
        metadata_output.get("inlinedResponses"),
        metadata_output.get("inlined_responses"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            responses = candidate.get("inlinedResponses") or candidate.get("inlined_responses") or []
            if isinstance(responses, list):
                return responses
        if isinstance(candidate, list):
            return candidate
    return []


def response_custom_id(item: Dict[str, Any]) -> Optional[str]:
    """@description Gemini 응답 metadata custom ID 추출"""
    metadata = item.get("metadata") or {}
    return (
        metadata.get("custom_id")
        or metadata.get("customId")
        or item.get("custom_id")
        or item.get("customId")
    )


def extract_raw_response(response_body: Dict[str, Any]) -> str:
    """@description Gemini 응답 텍스트 추출(추론 과정 제외)"""
    candidates = response_body.get("candidates", [])
    if not candidates:
        return ""

    content = candidates[0].get("content", {})
    if not isinstance(content, dict):
        return ""
    text_parts = []
    parts = content.get("parts", [])
    if not isinstance(parts, list):
        return ""
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("thought"):
            continue
        text = part.get("text")
        if isinstance(text, str):
            text_parts.append(text)
    return "".join(text_parts)


def completion_stats_counts(batch_data: Dict[str, Any]) -> Dict[str, int]:
    """@description Gemini Batch 응답 완료·실패·대기 수 계산"""
    metadata = batch_data.get("metadata") or {}
    stats = (
        batch_data.get("completionStats")
        or metadata.get("completionStats")
        or metadata.get("batchStats")
        or {}
    )
    total = stats.get("requestCount") or stats.get("totalRequestCount") or 0
    completed = stats.get("successfulRequestCount") or stats.get("successCount") or 0
    failed = stats.get("failedRequestCount") or stats.get("failureCount") or 0
    total = int(total or 0)
    completed = int(completed or 0)
    failed = int(failed or 0)

    responses = extract_inlined_responses(batch_data)
    if responses:
        total = total or len(responses)
        completed = completed or sum(1 for item in responses if not item.get("error"))
        failed = failed or sum(1 for item in responses if item.get("error"))

    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "pending": max(0, total - completed - failed),
    }


def check_batch_status(
    batch_id: str,
    model_config: ModelConfig,
    request_fn: Callable[..., dict],
) -> dict:
    """@description Gemini Batch 상태 공용 구조 변환"""
    batch_data = request_fn(
        "GET",
        resource_url(batch_id),
        model_config,
    )
    metadata = batch_data.get("metadata") or {}
    state = batch_data.get("state") or metadata.get("state") or "BATCH_STATE_UNSPECIFIED"
    counts = completion_stats_counts(batch_data)
    if state in GOOGLE_SUCCESS_STATES and counts["total"] and counts["completed"] == 0:
        counts["completed"] = counts["total"] - counts["failed"]
        counts["pending"] = 0

    return {
        "id": batch_data.get("name", batch_id),
        "status": state,
        "created_at": batch_data.get("createTime") or metadata.get("createTime"),
        "completed_at": batch_data.get("endTime") or metadata.get("endTime"),
        "failed_at": (
            batch_data.get("endTime") or metadata.get("endTime")
            if state in {"JOB_STATE_FAILED", "BATCH_STATE_FAILED"}
            else None
        ),
        "request_counts": counts,
        "raw": batch_data,
    }


def download_results(
    batch_id: str,
    model_config: ModelConfig,
    output_path: str,
    request_fn: Callable[..., dict],
    save_json_data: Callable[..., Path],
    display_path: Callable[[Path], str],
) -> Path:
    """@description Gemini Batch 결과 JSON 저장"""
    print(f"📥 Gemini 배치 결과 다운로드 중... (Batch ID: {batch_id})")
    batch_data = request_fn(
        "GET",
        resource_url(batch_id),
        model_config,
    )
    result_path = save_json_data(batch_data, output_path)
    print(f"✅ Gemini 결과 저장: {display_path(result_path)}")
    return result_path


def load_inlined_responses(result_path: Path) -> List[dict]:
    """@description Gemini 결과 파일 인라인 응답 목록 로드"""
    with open(result_path, "r", encoding="utf-8") as file:
        result_data = json.load(file)

    responses = extract_inlined_responses(result_data)
    if isinstance(responses, list):
        return responses
    return []


def parse_results(
    result_path: Path,
    model_name: str,
    input_custom_ids: Sequence[str] = (),
) -> List[dict]:
    """@description Gemini Batch 결과 파싱"""
    results = []
    for index, item in enumerate(load_inlined_responses(result_path)):
        custom_id = response_custom_id(item)
        if custom_id is None and index < len(input_custom_ids):
            custom_id = input_custom_ids[index]
        question_number = extract_question_number(custom_id)
        if question_number is None:
            continue

        if item.get("error"):
            error = item["error"]
            error_message = error.get("message", "Unknown error") if isinstance(error, dict) else str(error)
            results.append(
                {
                    "request_id": custom_id,
                    "question_number": question_number,
                    "model_name": model_name,
                    "raw_response": (
                        json.dumps(error, ensure_ascii=False)
                        if isinstance(error, (dict, list))
                        else str(error)
                    ),
                    "success": False,
                    "error_message": error_message,
                    "answer_status": "no_answer",
                    "error_details": error if isinstance(error, dict) else None,
                }
            )
            continue

        response_body = item.get("response") or item.get("result") or {}
        raw_response = extract_raw_response(response_body)
        usage_fields = extract_google_usage_fields(response_body.get("usageMetadata"))
        candidates = response_body.get("candidates", [])
        finish_reason = candidates[0].get("finishReason") if candidates else None
        prompt_feedback = response_body.get("promptFeedback") or {}
        is_refusal = bool(prompt_feedback.get("blockReason")) or finish_reason in {
            "SAFETY",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
        }
        if is_refusal and not raw_response:
            raw_response = json.dumps(
                prompt_feedback or {"finishReason": finish_reason},
                ensure_ascii=False,
            )
        has_generation = _has_response_or_token_usage(
            raw_response,
            usage_fields["input_tokens"],
            usage_fields["output_tokens"],
            usage_fields["total_tokens"],
        )
        results.append(
            {
                "request_id": custom_id,
                "question_number": question_number,
                "model_name": model_name,
                "raw_response": raw_response,
                "success": has_generation or is_refusal,
                "error_message": None if has_generation or is_refusal else EMPTY_RESPONSE_ERROR,
                "answer_status": "refusal" if is_refusal else "answered" if raw_response else "no_answer",
                "provider_stop_reason": finish_reason,
                **usage_fields,
            }
        )

    results.sort(key=lambda item: item["question_number"])
    print(f"✅ Gemini 결과 {len(results)}개 파싱 완료")
    return results


def parse_hard_results(
    result_path: Path,
    model_name: str,
    custom_id: str,
    input_custom_ids: Sequence[str] = (),
) -> List[dict]:
    """@description Gemini hard 섹션 Batch 결과 파싱"""
    results = []
    for index, item in enumerate(load_inlined_responses(result_path)):
        item_custom_id = response_custom_id(item)
        if item_custom_id is None and index < len(input_custom_ids):
            item_custom_id = input_custom_ids[index]
        if item_custom_id != custom_id:
            continue

        if item.get("error"):
            error = item["error"]
            error_message = error.get("message", "Unknown error") if isinstance(error, dict) else str(error)
            results.append(
                {
                    "question_number": 0,
                    "model_name": model_name,
                    "raw_response": (
                        json.dumps(error, ensure_ascii=False)
                        if isinstance(error, (dict, list))
                        else str(error)
                    ),
                    "success": False,
                    "error_message": error_message,
                    "answer_status": "no_answer",
                    "error_details": error if isinstance(error, dict) else None,
                }
            )
            continue

        response_body = item.get("response") or item.get("result") or {}
        finish_reason = None
        candidates = response_body.get("candidates", [])
        if candidates:
            finish_reason = candidates[0].get("finishReason")
        results.append(
            {
                "question_number": 0,
                "model_name": model_name,
                "raw_response": extract_raw_response(response_body),
                "success": True,
                "provider_stop_reason": finish_reason,
                **extract_google_usage_fields(response_body.get("usageMetadata")),
            }
        )

    print(f"✅ Gemini hard 결과 {len(results)}개 파싱 완료")
    return results


__all__ = [
    "GOOGLE_BATCH_POLL_SECONDS",
    "GOOGLE_GENAI_AVAILABLE",
    "GOOGLE_SUCCESS_STATES",
    "GOOGLE_TERMINAL_STATES",
    "batch_url",
    "check_batch_status",
    "completion_stats_counts",
    "create_batch",
    "download_results",
    "extract_inlined_responses",
    "extract_raw_response",
    "initialize_client",
    "load_inlined_responses",
    "parse_hard_results",
    "parse_results",
    "request",
    "resource_url",
    "response_custom_id",
]
