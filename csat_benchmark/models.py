"""@description API 실행기 공용 문항·모델·응답 자료 클래스"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .metadata import validate_knowledge_cutoff, validate_plan_message


EMPTY_RESPONSE_ERROR = "API returned neither response content nor token usage."
SUPPORTED_API_TYPES = frozenset(
    {"openai", "anthropic", "google", "deepseek", "grok", "friendli", "vllm"}
)


def _has_response_or_token_usage(
    raw_response: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    total_tokens: Optional[int],
) -> bool:
    """@description 응답 본문 또는 양수 토큰 사용량 존재 여부 확인"""
    if isinstance(raw_response, str) and raw_response.strip():
        return True
    return any(
        isinstance(token_count, (int, float))
        and not isinstance(token_count, bool)
        and token_count > 0
        for token_count in (input_tokens, output_tokens, total_tokens)
    )


@dataclass
class Question:
    """@description 수능 문제 자료 클래스"""

    number: int
    correct_answer: int
    points: int
    question_path: Optional[str] = None
    image_paths: Optional[List[str]] = None
    pdf_paths: Optional[List[str]] = None
    audio_paths: Optional[List[str]] = None
    video_paths: Optional[List[str]] = None
    question_text: Optional[str] = None
    elective: Optional[str] = None

    def __post_init__(self) -> None:
        """@description 선택 미디어 경로 기본값 초기화"""
        if self.image_paths is None:
            self.image_paths = []
        if self.pdf_paths is None:
            self.pdf_paths = []
        if self.audio_paths is None:
            self.audio_paths = []
        if self.video_paths is None:
            self.video_paths = []

    def load_question_text(self) -> str:
        """@description 문항 본문 파일 로드 및 파일 부재 시 빈 문자열 반환"""
        if self.question_text:
            return self.question_text

        if self.question_path:
            question_file = Path(self.question_path)
            if question_file.exists():
                with question_file.open("r", encoding="utf-8") as file:
                    self.question_text = file.read()
                return self.question_text

        return ""

    def encode_image(self, image_path: str) -> tuple[str, str]:
        """@description 이미지 base64 인코딩 및 MIME 타입 결합"""
        mime_type, _ = mimetypes.guess_type(image_path)
        if mime_type is None:
            mime_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }.get(Path(image_path).suffix.lower(), "image/png")

        with Path(image_path).open("rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("utf-8")
        return mime_type, encoded


@dataclass
class ModelConfig:
    """@description API 실행기 공용 모델 설정"""

    name: str
    api_type: str
    api_key: Union[str, List[str]]
    model_id: str
    max_tokens: int = 4096
    rate_limit_rpm: int = 10
    concurrent_request_limit: int = 50
    base_url: Optional[str] = None
    request_api: Optional[str] = None
    priority: int = 50
    reasoning_effort: Optional[str] = None
    reasoning_mode: Optional[str] = None
    thinking_budget: Optional[int] = None
    thinking_level: Optional[str] = None
    thinking_enabled: bool = False
    thinking_budget_tokens: Optional[int] = None
    friendli_thinking: bool = False
    supports_vision: bool = True
    price: Optional[Dict[str, float]] = None
    extra_body: Optional[Dict[str, Any]] = None
    vertex_key: Optional[str] = None
    modalities: Optional[List[str]] = None
    image_url_mode: str = "data_url"
    merge_multiple_images: bool = False
    batch_supported: bool = True
    comment: Optional[str] = None
    knowledge_cutoff: Optional[str] = None
    plan_message_ko: Optional[str] = None
    plan_message_en: Optional[str] = None

    def __post_init__(self) -> None:
        """@description API 타입·요청 제한값 검증"""
        if self.api_type not in SUPPORTED_API_TYPES:
            raise ValueError(f"지원하지 않는 API 타입입니다: {self.api_type}")
        for field_name in ("rate_limit_rpm", "concurrent_request_limit"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name}은 양의 정수여야 합니다.")
        self.knowledge_cutoff = validate_knowledge_cutoff(self.knowledge_cutoff)
        self.plan_message_ko = validate_plan_message(self.plan_message_ko, "plan_message_ko")
        self.plan_message_en = validate_plan_message(self.plan_message_en, "plan_message_en")


@dataclass
class APIResponse:
    """@description API 요청 응답·토큰 사용량 자료"""

    question_number: int
    model_name: str
    raw_response: str
    timestamp: str
    success: bool
    error_message: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    answer_status: Optional[str] = None
    provider_stop_reason: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """@description 본문·토큰 부재 성공 결과 → 실패 정규화"""
        if self.success and not _has_response_or_token_usage(
            self.raw_response,
            self.input_tokens,
            self.output_tokens,
            self.total_tokens,
        ):
            self.success = False
            self.error_message = EMPTY_RESPONSE_ERROR
            if self.answer_status is None:
                self.answer_status = "no_answer"
