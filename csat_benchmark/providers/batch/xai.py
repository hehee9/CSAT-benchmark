"""@description xAI native Batch API 전송·결과 파싱"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

from ...models import ModelConfig
from .common import (
    EMPTY_RESPONSE_ERROR,
    _has_response_or_token_usage,
    contains_refusal,
    extract_question_number,
    extract_usage_fields,
    flatten_text,
)


XAI_BATCH_ADD_INTERVAL_SECONDS = 2
XAI_BATCH_STATUS_POLL_SECONDS = 300
XAI_BATCH_REQUEST_CHUNK_SIZE = 25
XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"
XAI_RESULTS_PAGE_LIMIT = 100
XAI_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "expired"}


def initialize_client(model_config: ModelConfig) -> None:
    """@description xAI REST 모드 SDK 초기화 생략"""
    return None


def get_base_url(model_config: ModelConfig) -> str:
    """@description xAI Batch API 기본 URL 생성"""
    base_url = (model_config.base_url or XAI_DEFAULT_BASE_URL).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def headers(
    model_config: ModelConfig,
    resolve_api_key: Callable[[ModelConfig], str],
) -> Dict[str, str]:
    """@description xAI Batch API 요청 헤더 생성"""
    return {
        "Authorization": f"Bearer {resolve_api_key(model_config)}",
        "Content-Type": "application/json",
    }


def request(
    method: str,
    path: str,
    model_config: ModelConfig,
    resolve_api_key: Callable[[ModelConfig], str],
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """@description xAI Batch REST 요청 실행"""
    url = f"{get_base_url(model_config)}{path}"
    response = requests.request(
        method=method,
        url=url,
        headers=headers(model_config, resolve_api_key),
        json=json_body,
        params=params,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"xAI Batch API 요청 실패 ({response.status_code}) {method} {path}: {response.text}"
        )

    if not response.content:
        return {}

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"xAI Batch API 응답이 JSON이 아닙니다: {response.text}") from exc


def create_batch(
    model_config: ModelConfig,
    batch_name: str,
    request_fn: Callable[..., dict],
) -> dict:
    """@description xAI Batch 작업 생성"""
    print(f"🚀 xAI 배치 작업 생성 중... (name: {batch_name})")
    batch = request_fn(
        "POST",
        "/batches",
        model_config,
        json_body={"name": batch_name},
    )
    batch_id = batch.get("batch_id") or batch.get("id")
    if not batch_id:
        raise RuntimeError(f"xAI 배치 생성 응답에 batch_id가 없습니다: {batch}")

    print(f"✅ xAI 배치 작업 생성됨: {batch_id}")
    return batch


def add_batch_requests(
    batch_id: str,
    batch_requests: List[dict],
    model_config: ModelConfig,
    request_fn: Callable[..., dict],
    interval_seconds: int = XAI_BATCH_ADD_INTERVAL_SECONDS,
    chunk_size: int = XAI_BATCH_REQUEST_CHUNK_SIZE,
) -> None:
    """@description xAI 배치 요청 묶음 추가(고정 크기)"""
    print(
        f"📦 xAI 배치 요청 추가 시작: 총 {len(batch_requests)}개 "
        f"(chunk={chunk_size}, interval={interval_seconds}초)"
    )

    for index in range(0, len(batch_requests), chunk_size):
        chunk = batch_requests[index:index + chunk_size]
        chunk_number = index // chunk_size + 1
        total_chunks = (len(batch_requests) + chunk_size - 1) // chunk_size

        request_fn(
            "POST",
            f"/batches/{batch_id}/requests",
            model_config,
            json_body={
                "batch_requests": [
                    {"batch_request": request_body}
                    for request_body in chunk
                ]
            },
        )

        end_index = index + len(chunk)
        print(
            f"   청크 {chunk_number}/{total_chunks} 추가 완료 "
            f"({end_index}/{len(batch_requests)})"
        )

        if end_index < len(batch_requests):
            time.sleep(interval_seconds)


def derive_status(batch_data: dict) -> str:
    """@description xAI 응답 상태·집계 수치 기반 공용 상태 계산"""
    raw_status = batch_data.get("status")
    if isinstance(raw_status, str) and raw_status:
        return raw_status

    state = batch_data.get("state", {})
    state_status = state.get("status")
    if isinstance(state_status, str) and state_status:
        return state_status

    pending = state.get("num_pending", 0) or 0
    errored = state.get("num_error", 0) or 0
    canceled = state.get("num_cancelled", 0) or 0
    succeeded = state.get("num_success", 0) or 0
    total = state.get("num_requests", 0) or 0

    if pending > 0:
        return "in_progress"
    if canceled == total and total > 0:
        return "cancelled"
    if total > 0 and succeeded == 0 and errored > 0:
        return "failed"
    if total > 0 and pending == 0:
        return "completed"
    return "unknown"


def check_batch_status(
    batch_id: str,
    model_config: ModelConfig,
    request_fn: Callable[..., dict],
) -> dict:
    """@description xAI Batch 상태 공용 구조 변환"""
    batch_data = request_fn("GET", f"/batches/{batch_id}", model_config)
    state = batch_data.get("state", {})
    total = state.get("num_requests", 0) or 0
    pending = state.get("num_pending", 0) or 0
    succeeded = state.get("num_success", 0) or 0
    errored = state.get("num_error", 0) or 0
    canceled = state.get("num_cancelled", 0) or 0

    return {
        "id": batch_data.get("batch_id") or batch_data.get("id") or batch_id,
        "status": derive_status(batch_data),
        "created_at": batch_data.get("created_at"),
        "completed_at": batch_data.get("completed_at"),
        "failed_at": batch_data.get("failed_at"),
        "request_counts": {
            "total": total,
            "completed": succeeded + errored + canceled,
            "failed": errored,
            "pending": pending,
            "succeeded": succeeded,
            "cancelled": canceled,
        },
        "raw": batch_data,
    }


def download_results(
    batch_id: str,
    model_config: ModelConfig,
    output_path: str,
    request_fn: Callable[..., dict],
    save_json_data: Callable[..., Path],
) -> Path:
    """@description xAI Batch 결과 페이지 전체 저장"""
    print(f"📥 xAI 배치 결과 다운로드 중... (Batch ID: {batch_id})")

    pages = []
    pagination_token = None

    while True:
        params = {"limit": XAI_RESULTS_PAGE_LIMIT}
        if pagination_token:
            params["pagination_token"] = pagination_token

        page = request_fn(
            "GET",
            f"/batches/{batch_id}/results",
            model_config,
            params=params,
        )
        pages.append(page)

        pagination_token = (
            page.get("pagination_token")
            or page.get("next_pagination_token")
            or page.get("next_page_token")
        )
        if not pagination_token:
            break

    result_path = save_json_data({"batch_id": batch_id, "pages": pages}, output_path)
    print(f"✅ xAI 결과 저장: {result_path} ({len(pages)} page)")
    return result_path


def parse_results(result_path: Path, model_name: str) -> List[dict]:
    """@description xAI Batch 결과 파싱"""
    with open(result_path, "r", encoding="utf-8") as file:
        result_data = json.load(file)

    pages = result_data.get("pages", [])
    parsed_results = []

    for page in pages:
        for item in page.get("succeeded", []):
            request_id = item.get("batch_request_id") or item.get("request_id") or item.get("id")
            question_number = extract_question_number(request_id)
            if question_number is None:
                continue

            response_payload = item.get("response") or {}
            raw_response = flatten_text(response_payload)
            usage_fields = extract_usage_fields(
                response_payload.get("usage")
                if isinstance(response_payload, dict)
                else None
            )
            choices = response_payload.get("choices", []) if isinstance(response_payload, dict) else []
            choice = choices[0] if choices else {}
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            stop_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            refusal = message.get("refusal") if isinstance(message, dict) else None
            is_refusal = (
                stop_reason in {"refusal", "content_filter"}
                or isinstance(refusal, str)
                or contains_refusal(response_payload)
            )
            answer_status = (
                "refusal"
                if is_refusal
                else "answered" if raw_response else "no_answer"
            )
            has_generation = _has_response_or_token_usage(
                raw_response,
                usage_fields["input_tokens"],
                usage_fields["output_tokens"],
                usage_fields["total_tokens"],
            )
            parsed_results.append(
                {
                    "request_id": request_id,
                    "question_number": question_number,
                    "model_name": model_name,
                    "raw_response": raw_response,
                    "success": has_generation or is_refusal,
                    "error_message": None if has_generation or is_refusal else EMPTY_RESPONSE_ERROR,
                    "answer_status": answer_status,
                    "provider_stop_reason": stop_reason,
                    **usage_fields,
                }
            )

        for item in page.get("failed", []):
            request_id = item.get("batch_request_id") or item.get("request_id") or item.get("id")
            question_number = extract_question_number(request_id)
            if question_number is None:
                continue

            error = item.get("error")
            if isinstance(error, dict):
                error_message = error.get("message", "Unknown error")
            elif isinstance(error, str):
                error_message = error
            else:
                error_message = item.get("error_message", "Unknown error")

            parsed_results.append(
                {
                    "request_id": request_id,
                    "question_number": question_number,
                    "model_name": model_name,
                    "raw_response": (
                        json.dumps(error, ensure_ascii=False)
                        if isinstance(error, (dict, list))
                        else str(error)
                        if isinstance(error, str)
                        else json.dumps(item, ensure_ascii=False)
                    ),
                    "success": False,
                    "error_message": error_message,
                    "answer_status": "no_answer",
                    "error_details": error if isinstance(error, dict) else None,
                }
            )

    parsed_results.sort(key=lambda item: item["question_number"])
    print(f"✅ xAI 결과 {len(parsed_results)}개 파싱 완료")
    return parsed_results


def parse_hard_results(
    result_path: Path,
    model_name: str,
    custom_id: str,
) -> List[dict]:
    """@description xAI hard 섹션 Batch 결과 파싱"""
    with open(result_path, "r", encoding="utf-8") as file:
        result_data = json.load(file)

    parsed_results = []
    for page in result_data.get("pages", []):
        for item in page.get("succeeded", []):
            request_id = item.get("batch_request_id") or item.get("request_id") or item.get("id")
            if request_id != custom_id:
                continue
            parsed_results.append(
                {
                    "question_number": 0,
                    "model_name": model_name,
                    "raw_response": flatten_text(item.get("response")),
                    "success": True,
                }
            )

        for item in page.get("failed", []):
            request_id = item.get("batch_request_id") or item.get("request_id") or item.get("id")
            if request_id != custom_id:
                continue
            error = item.get("error")
            if isinstance(error, dict):
                error_message = error.get("message", "Unknown error")
            elif isinstance(error, str):
                error_message = error
            else:
                error_message = item.get("error_message", "Unknown error")
            parsed_results.append(
                {
                    "question_number": 0,
                    "model_name": model_name,
                    "raw_response": "",
                    "success": False,
                    "error_message": error_message,
                }
            )

    print(f"✅ xAI hard 결과 {len(parsed_results)}개 파싱 완료")
    return parsed_results


__all__ = [
    "XAI_BATCH_ADD_INTERVAL_SECONDS",
    "XAI_BATCH_REQUEST_CHUNK_SIZE",
    "XAI_BATCH_STATUS_POLL_SECONDS",
    "XAI_DEFAULT_BASE_URL",
    "XAI_RESULTS_PAGE_LIMIT",
    "XAI_TERMINAL_STATUSES",
    "add_batch_requests",
    "check_batch_status",
    "create_batch",
    "derive_status",
    "download_results",
    "get_base_url",
    "headers",
    "initialize_client",
    "parse_hard_results",
    "parse_results",
    "request",
]
