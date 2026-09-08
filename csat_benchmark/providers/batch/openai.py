"""@description OpenAI 호환 Batch API 전송·결과 파싱"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from ...models import ModelConfig
from .common import (
    EMPTY_RESPONSE_ERROR,
    _has_response_or_token_usage,
    contains_refusal,
    extract_question_number,
    extract_usage_fields,
    flatten_text,
)


try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None
    print("경고: OpenAI 패키지가 설치되지 않았습니다. OpenAI/DeepSeek 배치는 실행: pip install openai")


def initialize_client(
    model_config: ModelConfig,
    resolve_api_key: Callable[[ModelConfig], str],
) -> Any:
    """@description OpenAI 호환 SDK 클라이언트 초기화"""
    if not OPENAI_AVAILABLE:
        raise ImportError("OpenAI 패키지가 설치되지 않았습니다. 실행: pip install openai")

    api_key = resolve_api_key(model_config)
    if model_config.base_url:
        return OpenAI(api_key=api_key, base_url=model_config.base_url)
    return OpenAI(api_key=api_key)


def upload_file(client: Any, file_path: Path) -> str:
    """@description Batch 입력 파일 업로드 후 파일 ID 반환"""
    print(f"📤 파일 업로드 중: {file_path}")

    with open(file_path, "rb") as file:
        batch_file = client.files.create(file=file, purpose="batch")

    print(f"✅ 파일 업로드 완료: {batch_file.id}")
    return batch_file.id


def create_batch(client: Any, file_id: str, endpoint: str) -> str:
    """@description OpenAI 호환 Batch 작업 생성 후 ID 반환"""
    print(f"🚀 배치 작업 생성 중... (endpoint: {endpoint})")

    batch_job = client.batches.create(
        input_file_id=file_id,
        endpoint=endpoint,
        completion_window="24h",
    )

    print(f"✅ 배치 작업 생성됨: {batch_job.id}")
    print(f"   상태: {batch_job.status}")
    return batch_job.id


def check_batch_status(client: Any, batch_id: str) -> dict:
    """@description OpenAI 호환 Batch 상태 공용 구조 변환"""
    batch_job = client.batches.retrieve(batch_id)
    request_counts = getattr(batch_job, "request_counts", None)

    return {
        "id": batch_job.id,
        "status": batch_job.status,
        "created_at": batch_job.created_at,
        "completed_at": getattr(batch_job, "completed_at", None),
        "failed_at": getattr(batch_job, "failed_at", None),
        "request_counts": {
            "total": getattr(request_counts, "total", 0),
            "completed": getattr(request_counts, "completed", 0),
            "failed": getattr(request_counts, "failed", 0),
        },
    }


def download_results(
    client: Any,
    batch_id: str,
    output_path: str,
    resolve_workspace_path: Callable[[str], Path],
    display_path: Callable[[Path], str],
) -> Path:
    """@description OpenAI 호환 Batch 결과 원본 바이트 저장"""
    batch_job = client.batches.retrieve(batch_id)

    if not hasattr(batch_job, "output_file_id") or batch_job.output_file_id is None:
        raise RuntimeError("배치 작업에 결과 파일이 없습니다.")

    print(f"📥 결과 다운로드 중... (File ID: {batch_job.output_file_id})")

    result_content = client.files.content(batch_job.output_file_id).content

    result_path = resolve_workspace_path(output_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    with open(result_path, "wb") as file:
        file.write(result_content)

    print(f"✅ 결과 저장: {display_path(result_path)}")
    return result_path


def extract_raw_response(response_body: Dict[str, Any], use_responses_api: bool) -> str:
    """@description OpenAI 호환 Batch 응답 본문 텍스트 추출"""
    if use_responses_api:
        raw_response = response_body.get("output_text", "")
        if raw_response:
            return raw_response
        return flatten_text(response_body.get("output"))

    choices = response_body.get("choices", [])
    if choices:
        return flatten_text(choices[0].get("message"))
    return ""


def parse_results(
    result_path: Path,
    model_name: str,
    use_responses_api: bool = False,
) -> List[dict]:
    """@description OpenAI 호환 Batch 결과 파싱"""
    results = []

    with open(result_path, "r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            result_obj = json.loads(line)
            custom_id = result_obj["custom_id"]
            question_number = extract_question_number(custom_id)
            if question_number is None:
                continue

            if result_obj.get("error"):
                error = result_obj["error"]
                error_message = (
                    error.get("message", "Unknown error")
                    if isinstance(error, dict)
                    else str(error)
                )
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

            response_body = result_obj.get("response", {}).get("body", {})
            usage_fields = extract_usage_fields(response_body.get("usage"))
            raw_response = extract_raw_response(response_body, use_responses_api)
            choices = response_body.get("choices", [])
            choice = choices[0] if choices else {}
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            stop_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            refusal = message.get("refusal") if isinstance(message, dict) else None
            is_refusal = (
                stop_reason in {"refusal", "content_filter"}
                or isinstance(refusal, str)
                or contains_refusal(response_body)
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

            results.append(
                {
                    "request_id": custom_id,
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

    results.sort(key=lambda item: item["question_number"])
    print(f"✅ {len(results)}개 결과 파싱 완료")
    return results


def parse_hard_results(
    result_path: Path,
    model_name: str,
    custom_id: str,
    use_responses_api: bool = False,
) -> List[dict]:
    """@description OpenAI 호환 hard 섹션 Batch 결과 파싱"""
    results = []

    with open(result_path, "r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            result_obj = json.loads(line)
            if result_obj.get("custom_id") != custom_id:
                continue

            if result_obj.get("error"):
                results.append(
                    {
                        "question_number": 0,
                        "model_name": model_name,
                        "raw_response": "",
                        "success": False,
                        "error_message": result_obj["error"].get("message", "Unknown error"),
                    }
                )
                continue

            response_body = result_obj.get("response", {}).get("body", {})
            usage_fields = extract_usage_fields(response_body.get("usage"))
            results.append(
                {
                    "question_number": 0,
                    "model_name": model_name,
                    "raw_response": extract_raw_response(response_body, use_responses_api),
                    "success": True,
                    **usage_fields,
                }
            )

    print(f"✅ hard 결과 {len(results)}개 파싱 완료")
    return results


__all__ = [
    "OPENAI_AVAILABLE",
    "OpenAI",
    "check_batch_status",
    "create_batch",
    "download_results",
    "extract_raw_response",
    "initialize_client",
    "parse_hard_results",
    "parse_results",
    "upload_file",
]
