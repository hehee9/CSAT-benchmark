"""@description Anthropic Message Batches 전송·결과 파싱"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ...models import ModelConfig
from .common import (
    EMPTY_RESPONSE_ERROR,
    _has_response_or_token_usage,
    extract_anthropic_error_message,
    extract_question_number,
    extract_usage_fields,
    flatten_anthropic_content,
    load_json_objects,
)


try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None
    print("경고: Anthropic 패키지가 설치되지 않았습니다. Claude 배치는 실행: pip install anthropic")


def initialize_client(
    model_config: ModelConfig,
    resolve_api_key: Callable[[ModelConfig], str],
) -> Any:
    """@description Anthropic SDK 클라이언트 초기화"""
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("Anthropic 패키지가 설치되지 않았습니다. 실행: pip install anthropic")
    return Anthropic(api_key=resolve_api_key(model_config))


def create_batch(client: Any, batch_requests: List[dict]) -> dict:
    """@description Anthropic Message Batch 생성 후 dict 반환"""
    print("🚀 Anthropic Message Batch 생성 중...")
    batch = client.messages.batches.create(requests=batch_requests)
    batch_data = batch.to_dict()
    print(f"✅ Anthropic 배치 생성됨: {batch_data['id']}")
    print(f"   상태: {batch_data['processing_status']}")
    return batch_data


def check_batch_status(client: Any, batch_id: str) -> dict:
    """@description Anthropic Message Batch 상태 공용 구조 변환"""
    batch = client.messages.batches.retrieve(batch_id)
    batch_data = batch.to_dict(mode="json")
    counts = batch_data.get("request_counts", {})

    processing = counts.get("processing", 0)
    succeeded = counts.get("succeeded", 0)
    errored = counts.get("errored", 0)
    canceled = counts.get("canceled", 0)
    expired = counts.get("expired", 0)
    total = processing + succeeded + errored + canceled + expired

    return {
        "id": batch_data["id"],
        "status": batch_data["processing_status"],
        "created_at": batch_data.get("created_at"),
        "completed_at": batch_data.get("ended_at"),
        "failed_at": None,
        "request_counts": {
            "total": total,
            "completed": total - processing,
            "failed": errored + canceled + expired,
            "pending": processing,
            "succeeded": succeeded,
            "errored": errored,
            "cancelled": canceled,
            "expired": expired,
        },
        "raw": batch_data,
    }


def download_results(
    client: Any,
    batch_id: str,
    output_path: str,
    resolve_workspace_path: Callable[[str], Path],
    display_path: Callable[[Path], str],
) -> Path:
    """@description Anthropic Batch 결과 JSONL 저장"""
    print(f"📥 Anthropic 배치 결과 다운로드 중... (Batch ID: {batch_id})")
    result_path = resolve_workspace_path(output_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    with open(result_path, "w", encoding="utf-8") as file:
        for entry in client.messages.batches.results(batch_id):
            if hasattr(entry, "to_dict"):
                payload = entry.to_dict()
            else:
                payload = json.loads(entry.to_json())
            file.write(json.dumps(payload, ensure_ascii=False))
            file.write("\n")

    print(f"✅ Anthropic 결과 저장: {display_path(result_path)}")
    return result_path


def count_request_input_tokens(
    client: Any,
    request_params: Dict[str, Any],
) -> Optional[int]:
    """@description Anthropic 요청 입력 토큰 수 별도 API 조회"""
    allowed_keys = {"messages", "model", "system", "thinking", "tool_choice", "tools"}
    count_params = {
        key: value
        for key, value in request_params.items()
        if key in allowed_keys
    }

    try:
        counted = client.messages.count_tokens(**count_params)
    except Exception:
        return None

    input_tokens = getattr(counted, "input_tokens", None)
    return input_tokens if isinstance(input_tokens, int) else None


def parse_results(
    result_path: Path,
    model_name: str,
    model_config: Optional[ModelConfig] = None,
    request_params_by_custom_id: Optional[Dict[str, Dict[str, Any]]] = None,
    count_input_tokens: Optional[Callable[[Dict[str, Any], ModelConfig], Optional[int]]] = None,
) -> List[dict]:
    """@description Anthropic Message Batch 결과 파싱"""
    results = []

    for result_obj in load_json_objects(result_path):
        custom_id = result_obj.get("custom_id")
        question_number = extract_question_number(custom_id)
        if question_number is None:
            continue

        result_data = result_obj.get("result", {})
        result_type = result_data.get("type")

        if result_type == "succeeded" or "message" in result_data:
            message = result_data.get("message", {})
            stop_reason = message.get("stop_reason")
            raw_response = flatten_anthropic_content(message.get("content"))
            usage_fields = extract_usage_fields(message.get("usage"))
            if (
                usage_fields.get("output_tokens")
                and not usage_fields.get("input_tokens")
                and model_config is not None
                and request_params_by_custom_id
                and custom_id in request_params_by_custom_id
                and count_input_tokens is not None
            ):
                recounted_input_tokens = count_input_tokens(
                    request_params_by_custom_id[custom_id],
                    model_config,
                )
                if isinstance(recounted_input_tokens, int) and recounted_input_tokens > 0:
                    usage_fields["input_tokens"] = recounted_input_tokens
                    usage_fields["total_tokens"] = (
                        recounted_input_tokens + (usage_fields.get("output_tokens") or 0)
                    )
            is_refusal = stop_reason == "refusal"
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
                    "provider_stop_reason": stop_reason,
                    **usage_fields,
                }
            )
            continue

        if result_type == "errored":
            error_message = extract_anthropic_error_message(result_data)
        elif result_type == "canceled":
            error_message = "Batch request canceled"
        elif result_type == "expired":
            error_message = "Batch request expired"
        else:
            error_message = f"Unknown batch result type: {result_type}"

        results.append(
            {
                "request_id": custom_id,
                "question_number": question_number,
                "model_name": model_name,
                "raw_response": json.dumps(result_data, ensure_ascii=False),
                "success": False,
                "error_message": error_message,
                "answer_status": "technical_failure",
                "provider_stop_reason": None,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "error_details": result_data if isinstance(result_data, dict) else None,
            }
        )

    results.sort(key=lambda item: item["question_number"])
    print(f"✅ Anthropic 결과 {len(results)}개 파싱 완료")
    return results


def parse_hard_results(
    result_path: Path,
    model_name: str,
    custom_id: str,
    model_config: Optional[ModelConfig] = None,
    request_params_by_custom_id: Optional[Dict[str, Dict[str, Any]]] = None,
    count_input_tokens: Optional[Callable[[Dict[str, Any], ModelConfig], Optional[int]]] = None,
) -> List[dict]:
    """@description Anthropic hard 섹션 Batch 결과 파싱"""
    results = []

    for result_obj in load_json_objects(result_path):
        if result_obj.get("custom_id") != custom_id:
            continue

        result_data = result_obj.get("result", {})
        result_type = result_data.get("type")
        if result_type == "succeeded" or "message" in result_data:
            message = result_data.get("message", {})
            stop_reason = message.get("stop_reason")
            usage_fields = extract_usage_fields(message.get("usage"))
            if (
                usage_fields.get("output_tokens")
                and not usage_fields.get("input_tokens")
                and model_config is not None
                and request_params_by_custom_id
                and custom_id in request_params_by_custom_id
                and count_input_tokens is not None
            ):
                recounted_input_tokens = count_input_tokens(
                    request_params_by_custom_id[custom_id],
                    model_config,
                )
                if isinstance(recounted_input_tokens, int) and recounted_input_tokens > 0:
                    usage_fields["input_tokens"] = recounted_input_tokens
                    usage_fields["total_tokens"] = (
                        recounted_input_tokens + (usage_fields.get("output_tokens") or 0)
                    )
            results.append(
                {
                    "question_number": 0,
                    "model_name": model_name,
                    "raw_response": flatten_anthropic_content(message.get("content")),
                    "success": True,
                    "answer_status": "refusal" if stop_reason == "refusal" else "answered",
                    "provider_stop_reason": stop_reason,
                    **usage_fields,
                }
            )
            continue

        if result_type == "errored":
            error_message = extract_anthropic_error_message(result_data)
        elif result_type == "canceled":
            error_message = "Batch request canceled"
        elif result_type == "expired":
            error_message = "Batch request expired"
        else:
            error_message = f"Unknown batch result type: {result_type}"
        results.append(
            {
                "question_number": 0,
                "model_name": model_name,
                "raw_response": "",
                "success": False,
                "error_message": error_message,
                "answer_status": "no_answer",
                "provider_stop_reason": None,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            }
        )

    print(f"✅ Anthropic hard 결과 {len(results)}개 파싱 완료")
    return results


__all__ = [
    "ANTHROPIC_AVAILABLE",
    "Anthropic",
    "check_batch_status",
    "count_request_input_tokens",
    "create_batch",
    "download_results",
    "initialize_client",
    "parse_hard_results",
    "parse_results",
]
