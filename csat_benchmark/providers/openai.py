"""@description OpenAI·OpenAI 호환 공급자 클라이언트 구현"""

from __future__ import annotations

import base64
import json
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass

import requests

from ..models import APIResponse, ModelConfig, Question
from .base import APIClient, _append_stream_delta
from .requests import (
    build_chat_content,
    build_chat_options,
    build_responses_body,
    build_responses_content,
    get_mime_type,
)

OpenAI = None
httpx = None
OPENAI_AVAILABLE = False
PILImage = None
PIL_AVAILABLE = False
ALIBABA_CONTENT_REFUSAL_MARKER = (
    "Upstream error from Alibaba: Output data may contain inappropriate content."
)
STREAM_ERROR_CAPTURE_LIMIT = 64 * 1024

def _ensure_openai_available() -> bool:
    """@description OpenAI 계열 요청 시 OpenAI SDK 지연 로드"""
    global OpenAI, httpx, OPENAI_AVAILABLE
    if OPENAI_AVAILABLE:
        return True
    try:
        from openai import OpenAI as OpenAIClientClass
        import openai.resources.responses
        import openai.resources.chat
        import openai.resources.chat.completions  # noqa: F401 - SDK 기능 확인
        import httpx as httpx_module
    except ImportError:
        OPENAI_AVAILABLE = False
        return False
    OpenAI = OpenAIClientClass
    httpx = httpx_module
    OPENAI_AVAILABLE = True
    return True

def _ensure_pil_available() -> bool:
    """@description 로컬 이미지 병합 시 PIL 지연 로드"""
    global PILImage, PIL_AVAILABLE
    if PIL_AVAILABLE:
        return True
    try:
        from PIL import Image as ImageClass
    except ImportError:
        PIL_AVAILABLE = False
        return False
    PILImage = ImageClass
    PIL_AVAILABLE = True
    return True

@dataclass
class _StreamProgress:
    """@brief OpenAI 호환 스트림 수신 진행 상태"""
    stream_opened: bool = False
    generation_id: Optional[str] = None
    request_id: Optional[str] = None
    chunks_received: int = 0
    response_text: str = ""
    usage_info: Any = None
    usage_received: bool = False
    final_response: Any = None
    provider_stop_reason: Optional[str] = None
    refusal_detected: bool = False

def _create_recording_byte_stream(stream: Any,
                                  capture_limit: int = STREAM_ERROR_CAPTURE_LIMIT) -> Any:
    """
    @description SDK 원문 스트림 기록용 래퍼 생성(최대 크기 제한)

    @param stream 원본 httpx 동기 바이트 스트림
    @param capture_limit 기록 최대 바이트 수
    @return captured 기록 버퍼 포함 httpx 동기 바이트 스트림
    """
    class _HttpxRecordingByteStream(httpx.SyncByteStream):
        def __init__(self, source_stream: Any):
            self._source_stream = source_stream
            self.captured = bytearray()

        def __iter__(self):
            for chunk in self._source_stream:
                remaining = capture_limit - len(self.captured)
                if remaining > 0:
                    self.captured.extend(chunk[:remaining])
                yield chunk

        def close(self):
            self._source_stream.close()

    return _HttpxRecordingByteStream(stream)

class _UnframedStreamError(Exception):
    """@description SSE 외 공급자 오류용 요청 예외"""

    def __init__(self, body: Dict[str, Any], response: Any):
        message = body.get("message")
        if not isinstance(message, str) or not message:
            message = "Provider returned an unframed stream error."
        super().__init__(message)
        self.body = body
        self.response = response
        self.request = getattr(response, "request", None)
        code = body.get("code")
        self.status_code = code if isinstance(code, int) and not isinstance(code, bool) else None

def _parse_unframed_stream_error(raw_body: bytes) -> Optional[Dict[str, Any]]:
    """
    @description SSE 프레임 없는 JSON 본문 공급자 오류 추출

    @param raw_body 스트림 기록 원문 바이트
    @return 오류 객체 또는 None
    """
    try:
        payload = json.loads(raw_body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    return error if isinstance(error, dict) else None

class OpenAIClient(APIClient):
    """@description OpenAI API 클라이언트(GPT·OpenAI 호환 API)"""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        if not _ensure_openai_available():
            raise ImportError("OpenAI 패키지가 설치되지 않았습니다. 실행: pip install openai")

        # 타임아웃 설정: reasoning 모델·긴 응답용 30분
        # read 응답 대기 시간(스트리밍 청크 간격), write 요청 전송 시간, connect 연결 시간
        timeout = httpx.Timeout(
            timeout=1800.0,   # 전체 타임아웃 30분
            read=1800.0,      # 읽기 타임아웃 30분(reasoning 모델용)
            write=60.0,       # 쓰기 타임아웃 1분
            connect=10.0      # 연결 타임아웃 10초
        )

        self._timeout = timeout

        # base_url 지정 가능(DeepSeek·Grok 등 OpenAI 호환 API용)
        # 첫 번째 키 초기화(요청별 _get_next_api_key() 교체)
        initial_key = self._api_keys[0]
        if config.base_url:
            self.client = OpenAI(
                api_key=initial_key,
                base_url=config.base_url,
                timeout=timeout,
                max_retries=2
            )
        else:
            self.client = OpenAI(
                api_key=initial_key,
                timeout=timeout,
                max_retries=2
            )

    def _uses_responses_api(self) -> bool:
        request_api = (self.config.request_api or "").lower()
        if request_api == "responses":
            return True
        if request_api == "chat_completions":
            return False
        model_id = self.config.model_id.lower()
        return "codex" in model_id or model_id.startswith("gpt-5.6")

    def _is_openrouter(self) -> bool:
        return "openrouter.ai" in (self.config.base_url or "").lower()

    def _current_openrouter_api_key(self) -> str:
        api_key = getattr(self.client, "api_key", None)
        if isinstance(api_key, str) and api_key:
            return api_key
        return self._api_keys[0]

    def _get_mime_type(self, image_path: Path) -> str:
        return get_mime_type(image_path)

    def _should_merge_chat_images(self, question: Question) -> bool:
        return (
            self.config.supports_vision
            and not self._uses_responses_api()
            and self.config.merge_multiple_images
            and len(question.image_paths) >= 2
        )

    def _load_chat_image_payloads(self, question: Question) -> List[Dict[str, str]]:
        payloads: List[Dict[str, str]] = []

        if not self.config.supports_vision:
            return payloads

        existing_paths = [Path(path_str) for path_str in question.image_paths if Path(path_str).exists()]
        if not existing_paths:
            return payloads

        if self._should_merge_chat_images(question):
            merged_payload = self._merge_chat_images(existing_paths)
            if merged_payload is not None:
                return [merged_payload]

        for image_path in existing_paths:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()

            payloads.append({
                "mime_type": self._get_mime_type(image_path),
                "image_data": base64.b64encode(image_bytes).decode('utf-8')
            })

        return payloads

    def _merge_chat_images(self, image_paths: List[Path]) -> Optional[Dict[str, str]]:
        if not _ensure_pil_available():
            return None

        gap_px = 40
        opened_images = []
        try:
            for image_path in image_paths:
                with PILImage.open(image_path) as img:
                    opened_images.append(img.convert("RGBA"))

            if len(opened_images) < 2:
                return None

            max_width = max(img.width for img in opened_images)
            total_height = sum(img.height for img in opened_images) + gap_px * (len(opened_images) - 1)
            composite = PILImage.new("RGBA", (max_width, total_height), (255, 255, 255, 255))

            current_y = 0
            for img in opened_images:
                x_offset = (max_width - img.width) // 2
                composite.alpha_composite(img, (x_offset, current_y))
                current_y += img.height + gap_px

            output = BytesIO()
            composite.convert("RGB").save(output, format="PNG")
            return {
                "mime_type": "image/png",
                "image_data": base64.b64encode(output.getvalue()).decode('utf-8')
            }
        finally:
            for img in opened_images:
                img.close()

    def _build_responses_content(self, question: Question) -> List[Dict[str, Any]]:
        return build_responses_content(
            question,
            supports_vision=self.config.supports_vision,
            image_format="data_url",
            skip_missing=True,
        )

    def _build_chat_content(self, question: Question) -> List[Dict[str, Any]]:
        return build_chat_content(
            question,
            supports_vision=self.config.supports_vision,
            image_url_mode=self.config.image_url_mode,
            merge_multiple_images=self.config.merge_multiple_images,
            skip_missing=True,
        )

    def _build_chat_image_url(self, image_data: str, mime_type: str) -> str:
        if self.config.image_url_mode == "raw_base64":
            return image_data

        return f"data:{mime_type};base64,{image_data}"

    def _to_plain_data(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [self._to_plain_data(item) for item in value]
        if isinstance(value, dict):
            return {k: self._to_plain_data(v) for k, v in value.items()}
        if hasattr(value, "model_dump"):
            try:
                return self._to_plain_data(value.model_dump())
            except TypeError:
                pass
        if hasattr(value, "to_dict"):
            try:
                return self._to_plain_data(value.to_dict())
            except TypeError:
                pass
        if hasattr(value, "__dict__"):
            return self._to_plain_data(vars(value))
        return value

    def _extract_responses_text_delta(self, chunk: Any) -> str:
        chunk_data = self._to_plain_data(chunk)
        if not isinstance(chunk_data, dict):
            return ""

        if chunk_data.get("type") != "response.output_text.delta":
            return ""

        delta = chunk_data.get("delta")
        return delta if isinstance(delta, str) else ""

    def _extract_responses_refusal_delta(self, chunk: Any) -> str:
        """@description Responses API 거부 텍스트 조각 추출"""
        chunk_data = self._to_plain_data(chunk)
        if not isinstance(chunk_data, dict):
            return ""
        if chunk_data.get("type") != "response.refusal.delta":
            return ""
        delta = chunk_data.get("delta")
        return delta if isinstance(delta, str) else ""

    def _extract_response_output_text(self, response: Any) -> str:
        response_data = self._to_plain_data(response)
        if not response_data:
            return ""

        if isinstance(response_data, dict):
            output_text = response_data.get("output_text")
            if isinstance(output_text, str) and output_text:
                return output_text

        output_texts: List[str] = []

        def collect(node: Any):
            if isinstance(node, dict):
                node_type = node.get("type")
                if node_type == "output_text" and isinstance(node.get("text"), str):
                    output_texts.append(node["text"])
                elif node_type == "refusal" and isinstance(node.get("refusal"), str):
                    output_texts.append(node["refusal"])

                if "output" in node:
                    collect(node["output"])
                if "content" in node:
                    collect(node["content"])
            elif isinstance(node, list):
                for item in node:
                    collect(item)

        collect(response_data)
        return "".join(output_texts)

    def _response_contains_refusal(self, response: Any) -> bool:
        """@description Responses API 최종 응답의 거부 콘텐츠 포함 여부 확인"""
        response_data = self._to_plain_data(response)
        if isinstance(response_data, dict):
            if response_data.get("type") == "refusal":
                return True
            if isinstance(response_data.get("refusal"), str):
                return True
            return any(
                self._response_contains_refusal(response_data[key])
                for key in ("output", "content", "message", "response")
                if key in response_data
            )
        if isinstance(response_data, list):
            return any(self._response_contains_refusal(item) for item in response_data)
        return False

    def _extract_responses_stop_reason(self, value: Any) -> Optional[str]:
        """@description Responses API 종료 사유 추출"""
        data = self._to_plain_data(value)
        if not isinstance(data, dict):
            return None

        for field_name in ("stop_reason", "finish_reason"):
            reason = data.get(field_name)
            if isinstance(reason, str) and reason:
                return reason

        incomplete_details = data.get("incomplete_details")
        if isinstance(incomplete_details, dict):
            reason = incomplete_details.get("reason")
            if isinstance(reason, str) and reason:
                return reason

        response_data = data.get("response")
        if isinstance(response_data, dict):
            reason = self._extract_responses_stop_reason(response_data)
            if reason is not None:
                return reason

        status = data.get("status")
        if isinstance(status, str) and status not in {"queued", "in_progress"}:
            return status
        return None

    def _get_usage_field(self, usage_info: Any, field_name: str) -> Any:
        if isinstance(usage_info, dict):
            return usage_info.get(field_name)
        return getattr(usage_info, field_name, None)

    def _first_present_usage_field(self, usage_info: Any, *field_names: str) -> Any:
        for field_name in field_names:
            value = self._get_usage_field(usage_info, field_name)
            if value is not None:
                return value
        return None

    def _coerce_token_count(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _get_nested_usage_field(self, usage_info: Any, parent_name: str, field_name: str) -> Any:
        parent = self._get_usage_field(usage_info, parent_name)
        if parent is None:
            return None
        return self._get_usage_field(parent, field_name)

    def _first_present_nested_usage_field(self, usage_info: Any, *field_paths: Tuple[str, str]) -> Any:
        for parent_name, field_name in field_paths:
            value = self._get_nested_usage_field(usage_info, parent_name, field_name)
            if value is not None:
                return value
        return None

    def _extract_usage(self, usage_info: Any) -> tuple[Optional[int], Optional[int], Optional[int]]:
        input_tokens = self._coerce_token_count(
            self._first_present_usage_field(usage_info, 'prompt_tokens', 'input_tokens')
        )
        output_tokens = self._coerce_token_count(
            self._first_present_usage_field(usage_info, 'completion_tokens', 'output_tokens')
        )
        total_tokens = self._coerce_token_count(self._get_usage_field(usage_info, 'total_tokens'))
        nested_reasoning_tokens = self._first_present_nested_usage_field(
            usage_info,
            ('completion_tokens_details', 'reasoning_tokens'),
            ('output_tokens_details', 'reasoning_tokens')
        )
        reasoning_tokens = self._coerce_token_count(
            nested_reasoning_tokens
            if nested_reasoning_tokens is not None
            else self._get_usage_field(usage_info, 'reasoning_tokens')
        )

        if input_tokens is not None and total_tokens is not None:
            # xAI Grok 4.3 completion_tokens: 답변 토큰, total_tokens: 추론 토큰 포함
            # total_tokens - input_tokens 우선 적용: 추론 토큰 중복 합산 방지
            # 출력 토큰 필드 추론 토큰 포함 공급자 호환
            derived_output_tokens = total_tokens - input_tokens
            if derived_output_tokens >= 0:
                output_tokens = derived_output_tokens
        elif output_tokens is not None and reasoning_tokens:
            output_tokens += reasoning_tokens

        if output_tokens is None and input_tokens is not None and total_tokens is not None:
            output_tokens = total_tokens - input_tokens
        elif total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        return input_tokens, output_tokens, total_tokens

    def _extract_openrouter_generation_id(self, value: Any) -> Optional[str]:
        data = self._to_plain_data(value)
        if not isinstance(data, dict):
            return None

        for field_name in ("id", "generation_id"):
            field_value = data.get(field_name)
            if isinstance(field_value, str) and field_value:
                return field_value

        metadata = data.get("openrouter_metadata")
        if isinstance(metadata, dict):
            for field_name in ("id", "generation_id"):
                field_value = metadata.get(field_name)
                if isinstance(field_value, str) and field_value:
                    return field_value

        return None

    def _extract_openrouter_generation_usage(
        self,
        generation_data: Dict[str, Any]
    ) -> tuple[Optional[int], Optional[int], Optional[int]]:
        input_tokens = self._coerce_token_count(
            generation_data.get("native_tokens_prompt")
        )
        if input_tokens is None:
            input_tokens = self._coerce_token_count(generation_data.get("tokens_prompt"))

        visible_output_tokens = self._coerce_token_count(
            generation_data.get("native_tokens_completion")
        )
        if visible_output_tokens is None:
            visible_output_tokens = self._coerce_token_count(generation_data.get("tokens_completion"))

        reasoning_tokens = self._coerce_token_count(
            generation_data.get("native_tokens_reasoning")
        )
        output_tokens = None
        if visible_output_tokens is not None:
            output_tokens = visible_output_tokens + (reasoning_tokens or 0)
        elif reasoning_tokens is not None:
            output_tokens = reasoning_tokens

        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        return input_tokens, output_tokens, total_tokens

    def _fetch_openrouter_generation_usage(
        self,
        generation_id: Optional[str]
    ) -> tuple[Optional[int], Optional[int], Optional[int]]:
        if not generation_id:
            return None, None, None

        try:
            response = requests.get(
                "https://openrouter.ai/api/v1/generation",
                headers={"Authorization": f"Bearer {self._current_openrouter_api_key()}"},
                params={"id": generation_id},
                timeout=30
            )
            if response.status_code != 200:
                return None, None, None

            response_data = response.json()
            generation_data = response_data.get("data")
            if not isinstance(generation_data, dict):
                return None, None, None

            return self._extract_openrouter_generation_usage(generation_data)
        except Exception:
            return None, None, None

    def _needs_openrouter_usage_fallback(
        self,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        total_tokens: Optional[int]
    ) -> bool:
        if not self._is_openrouter():
            return False
        if input_tokens is None or output_tokens is None or total_tokens is None:
            return True
        return total_tokens != input_tokens + output_tokens

    def _merge_openrouter_usage_fallback(
        self,
        usage_tokens: tuple[Optional[int], Optional[int], Optional[int]],
        generation_id: Optional[str]
    ) -> tuple[Optional[int], Optional[int], Optional[int]]:
        input_tokens, output_tokens, total_tokens = usage_tokens
        if not self._needs_openrouter_usage_fallback(input_tokens, output_tokens, total_tokens):
            return usage_tokens

        fallback_tokens = self._fetch_openrouter_generation_usage(generation_id)
        fallback_input, fallback_output, fallback_total = fallback_tokens
        merged_input = fallback_input if fallback_input is not None else input_tokens
        merged_output = fallback_output if fallback_output is not None else output_tokens
        merged_total = fallback_total if fallback_total is not None else total_tokens

        if merged_total is None and merged_input is not None and merged_output is not None:
            merged_total = merged_input + merged_output
        elif merged_output is None and merged_input is not None and merged_total is not None:
            derived_output = merged_total - merged_input
            if derived_output >= 0:
                merged_output = derived_output

        return merged_input, merged_output, merged_total

    def _apply_chat_reasoning_params(self, api_params: Dict[str, Any]):
        if not self.config.reasoning_effort:
            return

        if self._is_openrouter():
            extra_body = api_params.setdefault("extra_body", {})
            reasoning = extra_body.setdefault("reasoning", {})
            reasoning.setdefault("effort", self.config.reasoning_effort)
            return

        api_params["reasoning_effort"] = self.config.reasoning_effort

    def _format_request_error(self, error: Exception) -> str:
        message = str(error)
        formatted_message = f"{type(error).__name__}: {message}" if message else type(error).__name__
        if "Multi Agent requests are not allowed on chat completions" in message:
            return (
                f"{formatted_message} | {self.config.model_id} 는 xAI Responses API 전용입니다. "
                "config에서 request_api를 'responses'로 설정해야 합니다."
            )
        return formatted_message

    def _capture_stream_headers(self, stream: Any, progress: _StreamProgress):
        """
        @description 스트림 응답 헤더 요청 식별자 보존

        @param stream OpenAI SDK 스트림 객체
        @param progress 요청 진행 상태
        """
        response = getattr(stream, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            return

        generation_id = headers.get("x-generation-id")
        if isinstance(generation_id, str) and generation_id:
            progress.generation_id = generation_id

        request_id = headers.get("x-request-id")
        if isinstance(request_id, str) and request_id:
            progress.request_id = request_id

    def _extract_provider_error(self, error: Exception) -> Optional[Dict[str, Any]]:
        """
        @description SDK 예외 본문 공급자 오류 허용 필드 추출

        @param error OpenAI SDK 요청 예외
        @return 허용 필드 포함 공급자 오류 또는 None
        """
        body = self._to_plain_data(getattr(error, "body", None))
        if not isinstance(body, dict):
            return None

        provider_error: Dict[str, Any] = {}
        code = body.get("code")
        if isinstance(code, (str, int, float)) and not isinstance(code, bool):
            provider_error["code"] = code

        for field_name in ("type", "param", "message"):
            field_value = body.get(field_name)
            if isinstance(field_value, str):
                provider_error[field_name] = field_value

        metadata = body.get("metadata")
        if isinstance(metadata, dict):
            error_type = metadata.get("error_type")
            if isinstance(error_type, str) and error_type:
                provider_error["error_type"] = error_type

            provider_code = metadata.get("provider_code")
            if isinstance(provider_code, (str, int, float)) and not isinstance(provider_code, bool):
                provider_error["provider_code"] = provider_code

        body_error_type = body.get("error_type")
        if "error_type" not in provider_error and isinstance(body_error_type, str) and body_error_type:
            provider_error["error_type"] = body_error_type

        return provider_error or None

    def _extract_exception_causes(self, error: Exception) -> List[Dict[str, str]]:
        """
        @description 연쇄 예외 클래스·메시지 추출

        @param error 원인 추적 대상 최상위 예외
        @return 예외 클래스·메시지 목록
        """
        causes: List[Dict[str, str]] = []
        seen = {id(error)}
        current = error

        while len(causes) < 5:
            next_error = current.__cause__
            if next_error is None and not current.__suppress_context__:
                next_error = current.__context__
            if next_error is None or id(next_error) in seen:
                break

            seen.add(id(next_error))
            causes.append({
                "exception_type": type(next_error).__name__,
                "message": str(next_error),
            })
            current = next_error

        return causes

    def _build_request_error_details(
        self,
        error: Exception,
        progress: _StreamProgress
    ) -> Dict[str, Any]:
        """
        @description 요청 실패 진단 정보 구성

        @param error 요청 처리 예외
        @param progress 요청 진행 상태
        @return 저장용 구조화 오류 정보
        """
        provider_error = self._extract_provider_error(error)
        response = getattr(error, "response", None)
        request = getattr(error, "request", None)
        if request is None and response is not None:
            request = getattr(response, "request", None)

        request_id = getattr(error, "request_id", None) or progress.request_id
        if request_id is None and response is not None:
            headers = getattr(response, "headers", None)
            if headers is not None:
                request_id = headers.get("x-request-id")

        http_status = getattr(error, "status_code", None)
        if http_status is None and provider_error:
            provider_code = provider_error.get("code")
            if isinstance(provider_code, int) and not isinstance(provider_code, bool):
                http_status = provider_code

        request_url = None
        if request is not None:
            url = getattr(request, "url", None)
            if url is not None:
                parsed_url = urlsplit(str(url))
                hostname = parsed_url.hostname
                if hostname:
                    if ":" in hostname and not hostname.startswith("["):
                        hostname = f"[{hostname}]"
                    netloc = hostname
                    if parsed_url.port is not None:
                        netloc = f"{netloc}:{parsed_url.port}"
                    request_url = urlunsplit((
                        parsed_url.scheme,
                        netloc,
                        parsed_url.path,
                        "",
                        ""
                    ))

        return {
            "exception_type": type(error).__name__,
            "exception_message": str(error),
            "causes": self._extract_exception_causes(error),
            "http_status": http_status,
            "request_id": request_id,
            "request_url": request_url,
            "provider_error": provider_error,
            "generation_id": progress.generation_id,
            "stream": {
                "opened": progress.stream_opened,
                "chunks_received": progress.chunks_received,
                "partial_response_chars": len(progress.response_text),
                "usage_received": progress.usage_received,
            },
        }

    def _is_alibaba_content_refusal_error(self, error_message: str) -> bool:
        """@description Alibaba 콘텐츠 검열 오류 여부 확인"""
        return ALIBABA_CONTENT_REFUSAL_MARKER in error_message

    def _build_chat_api_params(
        self,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        api_params = build_chat_options(
            self.config,
            stream=True,
            include_stream_usage=True,
            openrouter_reasoning=True,
            extra_body_mode="nested",
        )
        if self.system_prompt:
            api_params["messages"] = [
                {"role": "system", "content": self.system_prompt},
                *messages,
            ]
        else:
            api_params["messages"] = messages
        return api_params

    def _execute_chat_stream(
        self,
        api_params: Dict[str, Any],
        progress: _StreamProgress
    ):
        """
        @description Chat Completions 스트림 수집 및 실패 진단 상태 보존

        @param api_params Chat Completions 요청 인자
        @param progress 요청 진행 상태
        """
        stream = self.client.chat.completions.create(**api_params)
        progress.stream_opened = True
        self._capture_stream_headers(stream, progress)
        response = getattr(stream, "response", None)
        response_stream = getattr(response, "stream", None)
        recording_stream = None
        if response_stream is not None:
            recording_stream = _create_recording_byte_stream(response_stream)
            response.stream = recording_stream

        for chunk in stream:
            progress.chunks_received += 1
            chunk_generation_id = self._extract_openrouter_generation_id(chunk)
            if chunk_generation_id:
                progress.generation_id = chunk_generation_id
            if hasattr(chunk, 'usage') and chunk.usage:
                progress.usage_info = chunk.usage
                progress.usage_received = True
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            if isinstance(finish_reason, str) and finish_reason:
                progress.provider_stop_reason = finish_reason
                if finish_reason in {"refusal", "content_filter"}:
                    progress.refusal_detected = True
            delta = getattr(choice, "delta", None)
            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                progress.response_text = _append_stream_delta(
                    progress.response_text,
                    content,
                )
            refusal = getattr(delta, "refusal", None)
            if isinstance(refusal, str) and refusal:
                progress.response_text = _append_stream_delta(
                    progress.response_text,
                    refusal,
                )
                progress.refusal_detected = True

        if progress.chunks_received == 0 and recording_stream is not None:
            provider_error = _parse_unframed_stream_error(bytes(recording_stream.captured))
            if provider_error is not None:
                raise _UnframedStreamError(provider_error, response)

    def _execute_responses_stream(
        self,
        question: Question,
        progress: _StreamProgress,
    ) -> str:
        """@description Responses API 요청 전송 및 스트림 텍스트·사용량 수집"""
        api_params = build_responses_body(
            question,
            self.config,
            system_prompt=self.system_prompt,
            stream=True,
            image_format="data_url",
            reasoning_format="responses",
            include_extra_body=False,
        )

        stream = self.client.responses.create(**api_params)
        progress.stream_opened = True
        self._capture_stream_headers(stream, progress)

        for chunk in stream:
            progress.chunks_received += 1
            chunk_generation_id = self._extract_openrouter_generation_id(chunk)
            if chunk_generation_id:
                progress.generation_id = chunk_generation_id
            text_delta = self._extract_responses_text_delta(chunk)
            if text_delta:
                progress.response_text = _append_stream_delta(
                    progress.response_text,
                    text_delta,
                )
            refusal_delta = self._extract_responses_refusal_delta(chunk)
            if refusal_delta:
                progress.response_text = _append_stream_delta(
                    progress.response_text,
                    refusal_delta,
                )
                progress.refusal_detected = True
                progress.provider_stop_reason = "refusal"
            if hasattr(chunk, 'usage') and chunk.usage:
                progress.usage_info = chunk.usage
                progress.usage_received = True
            chunk_data = self._to_plain_data(chunk)
            if isinstance(chunk_data, dict):
                if chunk_data.get("usage"):
                    progress.usage_info = chunk_data["usage"]
                    progress.usage_received = True
                if chunk_data.get("response"):
                    progress.final_response = chunk_data["response"]
            response = getattr(chunk, 'response', None)
            if response:
                progress.final_response = response
            stop_reason = self._extract_responses_stop_reason(chunk)
            if stop_reason is not None and not (
                progress.refusal_detected and stop_reason == "completed"
            ):
                progress.provider_stop_reason = stop_reason

        raw_response = progress.response_text
        if not raw_response and progress.final_response is not None:
            raw_response = self._extract_response_output_text(progress.final_response)
        if progress.final_response is not None:
            progress.refusal_detected = (
                progress.refusal_detected
                or self._response_contains_refusal(progress.final_response)
            )
            if progress.refusal_detected and progress.provider_stop_reason in {
                None,
                "completed",
            }:
                progress.provider_stop_reason = "refusal"
        if progress.usage_info is None and progress.final_response is not None:
            progress.usage_info = getattr(progress.final_response, 'usage', None)
            if progress.usage_info is None:
                final_response_data = self._to_plain_data(progress.final_response)
                if isinstance(final_response_data, dict):
                    progress.usage_info = final_response_data.get("usage")
            if progress.usage_info is not None:
                progress.usage_received = True
        if progress.provider_stop_reason is None and progress.final_response is not None:
            progress.provider_stop_reason = self._extract_responses_stop_reason(
                progress.final_response
            )

        return raw_response

    def send_request(self, question: Question) -> APIResponse:
        """@description OpenAI API 스트리밍 요청 전송"""
        # 요청별 API 키 로테이션
        self.client.api_key = self._get_next_api_key()
        progress = _StreamProgress()

        try:
            if self._uses_responses_api():
                raw_response = self._execute_responses_stream(question, progress)

            else:
                messages = []
                content = self._build_chat_content(question)
                messages.append({"role": "user", "content": content})
                api_params = self._build_chat_api_params(messages)
                self._execute_chat_stream(api_params, progress)
                raw_response = progress.response_text

            input_tokens = None
            output_tokens = None
            total_tokens = None
            if progress.usage_info:
                input_tokens, output_tokens, total_tokens = self._extract_usage(progress.usage_info)
            input_tokens, output_tokens, total_tokens = self._merge_openrouter_usage_fallback(
                (input_tokens, output_tokens, total_tokens),
                progress.generation_id
            )

            answer_status = (
                "refusal"
                if progress.refusal_detected
                else "answered" if raw_response else "no_answer"
            )

            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response=raw_response,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                answer_status=answer_status,
                provider_stop_reason=progress.provider_stop_reason,
            )

        except Exception as e:
            error_message = self._format_request_error(e)
            if self._is_alibaba_content_refusal_error(error_message):
                return APIResponse(
                    question_number=question.number,
                    model_name=self.config.name,
                    raw_response="",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    success=True,
                    answer_status="refusal",
                    provider_stop_reason="refusal"
                )
            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response="",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=False,
                error_message=error_message,
                error_details=self._build_request_error_details(e, progress)
            )
