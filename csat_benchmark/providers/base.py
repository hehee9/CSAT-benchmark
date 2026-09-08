"""@description 공급자 클라이언트 공통 기본 동작"""

from __future__ import annotations

import threading
from typing import Optional

from ..models import APIResponse, ModelConfig, Question


def _append_stream_delta(current_text: str, incoming_delta: str) -> str:
    """@description 스트림 텍스트 조각 연결"""
    return current_text + incoming_delta


class APIClient:
    """@description 공급자 API 클라이언트 기본 클래스"""

    system_prompt: Optional[str] = None

    def __init__(self, config: ModelConfig):
        self.config = config
        self.system_prompt = None

        # API 키 로테이션 설정
        if isinstance(config.api_key, list):
            self._api_keys = config.api_key
        else:
            self._api_keys = [config.api_key]
        self._key_index = 0
        self._key_lock = threading.Lock()

    def _get_next_api_key(self) -> str:
        """
        @description 다음 API 키 라운드 로빈 반환
        @return API 키 문자열
        """
        with self._key_lock:
            key = self._api_keys[self._key_index % len(self._api_keys)]
            self._key_index += 1
            return key

    def send_request(self, question: Question) -> APIResponse:
        """@description API 요청 전송 인터페이스(하위 클래스 구현)"""
        raise NotImplementedError
