"""@description Gemini 4 Argon 응답과 추론 수준 지원 여부 확인"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from csat_benchmark.configuration import load_config


MODEL_NAME = "Gemini 4 Argon (low)"
PROMPT = "just say ok"
THINKING_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
POLL_INTERVAL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 120
_THINKING_LEVEL_FIELD = re.compile(r"thinking(?:_|\s)?level", re.IGNORECASE)
_LEVEL_REJECTION = re.compile(
    r"\b(?:invalid|unsupported|not supported|not allowed|must be|expected|unrecognized|not recognized)\b",
    re.IGNORECASE,
)


def _timestamp() -> str:
    """@description 현재 시각을 UTC ISO 형식으로 반환"""
    return datetime.now(timezone.utc).isoformat()


def _redact(value: str | None, api_key: str) -> str | None:
    """@description 저장·출력용 문자열에서 API 키 제거"""
    if value is None:
        return None
    return value.replace(api_key, "[REDACTED]")


def _save_state(output_path: Path, state: dict[str, Any]) -> None:
    """@description 진행 상태를 JSON 파일에 저장"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _response_text(payload: dict[str, Any] | None) -> str:
    """@description 응답 후보에서 추론 조각을 제외한 텍스트 연결"""
    if payload is None:
        return ""
    text_parts = []
    for candidate in payload.get("candidates", []):
        parts = candidate.get("content", {}).get("parts", [])
        for part in parts:
            if not part.get("thought", False) and "text" in part:
                text_parts.append(part["text"])
    return "".join(text_parts)


def _explicit_level_rejection(status_code: int | None, error_body: str | None) -> bool:
    """@description thinkingLevel 값을 명시적으로 거부한 400 응답 판별"""
    if status_code != 400 or error_body is None:
        return False
    field_match = _THINKING_LEVEL_FIELD.search(error_body)
    if field_match is None:
        return False
    related_message = error_body[max(0, field_match.start() - 100) : field_match.end() + 160]
    return _LEVEL_REJECTION.search(related_message) is not None


def _request_level(model_id: str, api_key: str, level: str) -> dict[str, Any]:
    """@description AIS generateContent 요청 1회의 결과 정리"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": level.upper()}},
    }
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        return {
            "status_code": None,
            "text": None,
            "error_body": None,
            "error": _redact(str(error), api_key),
            "classification": "inconclusive",
        }

    body = response.text
    status_code = response.status_code
    try:
        response_payload = json.loads(body)
    except json.JSONDecodeError:
        response_payload = None
    text = _response_text(response_payload)

    if 200 <= status_code < 300 and text.strip():
        classification = "supported"
        error_body = None
    elif _explicit_level_rejection(status_code, body):
        classification = "unsupported"
        error_body = body
    else:
        classification = "inconclusive"
        error_body = body

    return {
        "status_code": status_code,
        "text": text,
        "error_body": _redact(error_body, api_key),
        "error": None,
        "classification": classification,
    }


def _run_probe(config_path: Path, output_path: Path, model_id_override: str | None = None) -> None:
    """@description 첫 답변까지 반복 확인하고 추론 수준 지원 표 완성"""
    config = load_config(config_path, model_names=[MODEL_NAME])
    model = config["models"][0]
    api_key = model["api_key"]
    model_id = model_id_override if model_id_override is not None else model["model_id"]
    state: dict[str, Any] = {
        "state": "waiting",
        "model_id": model_id,
        "prompt": PROMPT,
        "poll_attempts": 0,
        "last_poll": None,
        "thinking_levels": {},
        "summary": None,
    }
    _save_state(output_path, state)

    previous_poll_start: float | None = None
    while state["state"] == "waiting":
        if previous_poll_start is not None:
            remaining = POLL_INTERVAL_SECONDS - (time.monotonic() - previous_poll_start)
            if remaining > 0:
                time.sleep(remaining)

        started = time.monotonic()
        previous_poll_start = started
        state["poll_attempts"] += 1
        state["last_poll"] = {
            "attempt": state["poll_attempts"],
            "started_at": _timestamp(),
            "status_code": None,
            "text": None,
            "error_body": None,
            "error": None,
        }
        _save_state(output_path, state)
        result = _request_level(model_id, api_key, "low")
        state["last_poll"].update(
            {key: result[key] for key in ("status_code", "text", "error_body", "error")}
        )
        if result["classification"] == "supported":
            state["state"] = "testing"
            state["thinking_levels"] = {
                level: {
                    "status": "pending",
                    "attempts": 0,
                    "last_attempt_at": None,
                    "status_code": None,
                    "text": None,
                    "error_body": None,
                    "error": None,
                }
                for level in THINKING_LEVELS
            }
            print("첫 답변을 확인해 추론 수준 7개를 검사합니다.")
        else:
            code = result["status_code"] if result["status_code"] is not None else "연결 오류"
            print(f"응답 대기 {state['poll_attempts']}회차: {code}, 60초 간격으로 계속 확인합니다.")
        _save_state(output_path, state)

    last_level_starts: dict[str, float | None] = {level: None for level in THINKING_LEVELS}
    while any(item["status"] == "pending" for item in state["thinking_levels"].values()):
        now = time.monotonic()
        ready = [
            level
            for level in THINKING_LEVELS
            if state["thinking_levels"][level]["status"] == "pending"
            and (
                last_level_starts[level] is None
                or now - last_level_starts[level] >= POLL_INTERVAL_SECONDS
            )
        ]
        if not ready:
            next_due = min(
                last_level_starts[level] + POLL_INTERVAL_SECONDS
                for level in THINKING_LEVELS
                if state["thinking_levels"][level]["status"] == "pending"
                and last_level_starts[level] is not None
            )
            time.sleep(max(0, next_due - now))
            continue

        level = ready[0]
        started = time.monotonic()
        last_level_starts[level] = started
        item = state["thinking_levels"][level]
        item["attempts"] += 1
        item["last_attempt_at"] = _timestamp()
        item["status_code"] = None
        item["text"] = None
        item["error_body"] = None
        item["error"] = None
        _save_state(output_path, state)

        result = _request_level(model_id, api_key, level)
        item.update({key: result[key] for key in ("status_code", "text", "error_body", "error")})
        if result["classification"] in ("supported", "unsupported"):
            item["status"] = result["classification"]
        code = result["status_code"] if result["status_code"] is not None else "연결 오류"
        label = {"supported": "지원", "unsupported": "미지원", "inconclusive": "판정 보류"}[
            result["classification"]
        ]
        print(f"{level}: {label} (HTTP {code})")
        _save_state(output_path, state)

    supported = [
        level for level in THINKING_LEVELS if state["thinking_levels"][level]["status"] == "supported"
    ]
    unsupported = [
        level for level in THINKING_LEVELS if state["thinking_levels"][level]["status"] == "unsupported"
    ]
    state["state"] = "completed"
    state["summary"] = {"supported_levels": supported, "unsupported_levels": unsupported}
    _save_state(output_path, state)
    print(f"검사 완료: 지원 {', '.join(supported) or '없음'} / 미지원 {', '.join(unsupported) or '없음'}")


def main(argv: list[str] | None = None) -> int:
    """@description 설정·저장 경로를 받아 Gemini Argon 검사 실행"""
    parser = argparse.ArgumentParser(description="Gemini 4 Argon 응답 및 추론 수준 지원 검사")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "logs" / "gemini-argon-probe.json")
    parser.add_argument("--model-id", help="구성 파일의 모델 식별자 대신 사용할 모델 ID")
    args = parser.parse_args(argv)
    _run_probe(args.config, args.output, args.model_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
