"""@description OpenRouter Batch API 전송 및 결과 파싱"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from .common import extract_question_number
from .openai import _response_record


def enabled(config):
    """@description OpenRouter 모델 설정 판별"""
    return config.api_type == "openai" and urlparse(config.base_url or "").hostname == "openrouter.ai"


def request(method, path, config, resolve_api_key, error_type, *, json_body=None, sleep=time.sleep):
    """@description OpenRouter Batch REST 요청"""
    for attempt in range(25):
        response = requests.request(
            method, f"https://openrouter.ai/api/v1{path}",
            headers={"Authorization": f"Bearer {resolve_api_key(config)}"},
            json=json_body, timeout=120,
        )
        if method != "GET" or response.status_code != 404 or attempt == 24:
            break
        sleep(5)
    if response.status_code == 402:
        raise error_type("OpenRouter 잔액 부족으로 결과를 받을 수 없습니다. 크레딧 충전 후 다시 조회하세요(재제출 불필요).")
    if not response.ok:
        raise error_type(f"OpenRouter Batch API 요청 실패 ({response.status_code}): {response.text}")
    return response.json()


def create_payload(config, batch_requests):
    """@description OpenRouter 배치 제출 본문 구성"""
    payload = {"endpoint": "/v1/chat/completions", "model": config.model_id}
    provider = (config.extra_body or {}).get("provider", {})
    if provider.get("order"):
        payload["provider"] = {"only": provider["order"], "allow_fallbacks": False}
    payload["completion_window"] = "24h"
    payload["requests"] = []
    for item in batch_requests:
        body = dict(item["body"])
        reasoning_effort = body.pop("reasoning_effort", None)
        if "reasoning" not in body and reasoning_effort is not None:
            body["reasoning"] = {"effort": reasoning_effort}
        for key in ("model", "stream", "provider", "extra_body"):
            body.pop(key, None)
        payload["requests"].append({"custom_id": item["custom_id"], "body": body})
    return payload


def check_batch_status(batch_id, config, request_fn):
    """@description OpenRouter 배치 상태 공용 구조 변환"""
    data = request_fn("GET", f"/batches/{batch_id}", config)
    status = data["status"]
    if status == "completed" and data["results"] is None:
        status = "finalizing"
    return {
        "id": data["id"], "status": status, "created_at": data["created_at"],
        "completed_at": data["finalized_at"] if status == "completed" else None,
        "failed_at": data["finalized_at"] if status == "failed" else None,
        "request_counts": data["request_counts"], "raw": data,
    }


def download_results(batch_id, config, output_path, request_fn, save_json):
    """@description OpenRouter 인라인 결과 저장"""
    data = request_fn("GET", f"/batches/{batch_id}", config)
    if data["status"] == "completed" and data["results"] is None:
        raise RuntimeError("OpenRouter 배치 결과가 아직 준비되지 않았습니다. 다시 조회하세요.")
    return save_json(data, output_path)


def parse_results(result_path: Path, model_name: str):
    """@description OpenRouter 인라인 결과를 공용 레코드로 변환"""
    data = json.loads(result_path.read_text(encoding="utf-8"))
    results = []
    for item in data["results"] or []:
        custom_id = item["custom_id"]
        number = extract_question_number(custom_id)
        if number is None:
            continue
        response = item["response"]
        error = item["error"]
        if error is not None or response["status_code"] != 200:
            error = error if error is not None else response["body"].get("error", response["body"])
            default_message = f"HTTP {response['status_code']}" if response else "Unknown error"
            message = error.get("message", default_message) if isinstance(error, dict) else str(error)
            results.append({
                "request_id": custom_id,
                "question_number": number,
                "model_name": model_name,
                "raw_response": json.dumps(error, ensure_ascii=False) if isinstance(error, (dict, list)) else str(error),
                "success": False,
                "error_message": message,
                "answer_status": "no_answer",
                "error_details": error if isinstance(error, dict) else None,
            })
        else:
            results.append(_response_record(custom_id, number, model_name, response["body"], False))
    results.sort(key=lambda item: item["question_number"])
    return results
