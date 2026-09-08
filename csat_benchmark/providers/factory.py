"""@description 공용 모델 설정 기반 공급자 클라이언트 생성 진입점"""

from __future__ import annotations

from typing import Any, Optional

from ..models import ModelConfig
from .anthropic import AnthropicClient
from .google import GoogleClient
from .openai import OpenAIClient


def create_provider_client(
    config: ModelConfig,
    system_prompt: Optional[str] = None,
) -> Any:
    """
    @description 모델 설정 기반 즉시 실행 공급자 클라이언트 생성

    @param config 공용 모델 설정
    @param system_prompt 요청용 시스템 지침(선택 사항)
    @return ``send_request(question)`` 제공 공급자 클라이언트
    @throws ValueError 미지원 API 타입
    """
    client_classes = {
        "openai": OpenAIClient,
        "deepseek": OpenAIClient,
        "grok": OpenAIClient,
        "friendli": OpenAIClient,
        "vllm": OpenAIClient,
        "anthropic": AnthropicClient,
        "google": GoogleClient,
    }
    try:
        client_class = client_classes[config.api_type]
    except KeyError as error:
        raise ValueError(f"지원하지 않는 API 타입입니다: {config.api_type}") from error
    client = client_class(config)
    client.system_prompt = system_prompt
    return client
