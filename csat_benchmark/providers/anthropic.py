"""@description Anthropic 공급자 클라이언트 구현"""

from __future__ import annotations

import json
import time

import requests

from ..models import APIResponse, ModelConfig, Question
from .base import APIClient
from .requests import build_anthropic_params



class AnthropicClient(APIClient):
    """@description Anthropic API 클라이언트(Claude 모델·REST 방식)"""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.api_url = "https://api.anthropic.com/v1/messages"

    def _parse_streaming_response(self, response) -> tuple:
        """@description Server-Sent Events(SSE) 스트리밍 응답 파싱

        @return (text, usage_dict, stop_reason) 응답 텍스트·토큰 사용량·종료 사유
        """
        text_parts = []
        usage_info = {'input_tokens': None, 'output_tokens': None, 'total_tokens': None}
        stop_reason = None

        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode('utf-8')

            # SSE 형식 "data: {...}" 라인 처리
            if line.startswith('data: '):
                try:
                    data_str = line[6:]  # "data: " 접두사 제거
                    data = json.loads(data_str)

                    # message_start 이벤트 input_tokens 추출
                    if data.get('type') == 'message_start':
                        message = data.get('message', {})
                        usage = message.get('usage', {})
                        usage_info['input_tokens'] = usage.get('input_tokens')

                    # content_block_delta 이벤트 텍스트 추출
                    if data.get('type') == 'content_block_delta':
                        delta = data.get('delta', {})
                        if delta.get('type') == 'text_delta':
                            text = delta.get('text', '')
                            if text:
                                text_parts.append(text)

                    # message_delta 이벤트 output_tokens 추출
                    if data.get('type') == 'message_delta':
                        delta = data.get('delta', {})
                        candidate_stop_reason = delta.get('stop_reason')
                        if candidate_stop_reason:
                            stop_reason = candidate_stop_reason
                        usage = data.get('usage', {})
                        usage_info['output_tokens'] = usage.get('output_tokens')

                except json.JSONDecodeError:
                    # ping 등 JSON 파싱 실패 이벤트 무시
                    pass

        return ''.join(text_parts), usage_info, stop_reason

    def send_request(self, question: Question) -> APIResponse:
        """@description Anthropic REST API 요청 전송"""
        # 요청별 API 키 로테이션
        current_key = self._get_next_api_key()

        try:
            # 요청 헤더 구성
            headers = {
                "x-api-key": current_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"  # API 버전 명시
            }

            # 요청 본문 구성
            payload = build_anthropic_params(
                question,
                self.config,
                system_prompt=self.system_prompt,
            )
            payload["stream"] = True

            # REST API 요청 전송(스트리밍)
            response = requests.post(self.api_url, headers=headers, json=payload, stream=True, timeout=(30, 6000))

            # 응답 처리
            if response.status_code != 200:
                raise Exception(f"API Error {response.status_code}: {response.text}")

            # Server-Sent Events 스트리밍 응답 파싱
            raw_response, usage_info, stop_reason = self._parse_streaming_response(response)

            # 토큰 사용량 계산
            input_tokens = usage_info.get('input_tokens')
            output_tokens = usage_info.get('output_tokens')
            total_tokens = None
            if input_tokens is not None and output_tokens is not None:
                total_tokens = input_tokens + output_tokens

            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response=raw_response,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                answer_status=(
                    "refusal"
                    if stop_reason == "refusal"
                    else "answered" if raw_response else "no_answer"
                ),
                provider_stop_reason=stop_reason,
            )

        except Exception as e:
            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response="",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=False,
                error_message=str(e)
            )
