"""@description 공급자 클라이언트 대표 요청·응답 계약 검증"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from csat_benchmark.models import ModelConfig, Question
from csat_benchmark.providers import (
    APIClient,
    AnthropicClient,
    GoogleClient,
    OpenAIClient,
)
from csat_benchmark.providers.factory import create_provider_client
from csat_benchmark.providers import google as google_provider
from csat_benchmark.providers import openai as openai_provider
from csat_benchmark.providers import anthropic as anthropic_provider
import csat_benchmark.providers as providers


def _config(api_type: str, **overrides: Any) -> ModelConfig:
    """@description 모의 요청 테스트용 모델 설정 생성"""
    values = {
        "name": f"{api_type} 테스트",
        "api_type": api_type,
        "api_key": ["key-1", "key-2"],
        "model_id": "test-model",
        "max_tokens": 64,
        "rate_limit_rpm": 10,
        "concurrent_request_limit": 1,
        "supports_vision": True,
        "base_url": "https://example.test/v1",
    }
    values.update(overrides)
    return ModelConfig(**values)


def _question() -> Question:
    """@description 텍스트 전용 대표 문항 생성"""
    return Question(number=7, correct_answer=3, points=2, question_text="문항 본문")


def _chunk(text: str, usage: Any = None) -> Any:
    """@description OpenAI 호환 스트림 청크 생성"""
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
        usage=usage,
    )


def test_provider_exports_expose_only_retained_client_contract():
    """@description 공용 공급자 클라이언트 공개 계약 확인"""
    assert APIClient is not None
    assert not hasattr(providers, "AnthropicClient_backup")
    assert OpenAIClient.__module__ == "csat_benchmark.providers.openai"
    assert AnthropicClient.__module__ == "csat_benchmark.providers.anthropic"
    assert GoogleClient.__module__ == "csat_benchmark.providers.google"


def test_factory_creates_retained_provider_classes_with_mocked_sdk_constructors(monkeypatch):
    """@description 유지 공급자 팩토리·모의 SDK 생성 확인"""
    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeGoogle:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(google_provider, "_ensure_google_available", lambda: True)
    monkeypatch.setattr(google_provider, "GOOGLE_GENAI_AVAILABLE", True)
    monkeypatch.setattr(google_provider, "genai", SimpleNamespace(Client=FakeGoogle))

    for api_type, expected_class in (
        ("openai", OpenAIClient),
        ("deepseek", OpenAIClient),
        ("grok", OpenAIClient),
        ("friendli", OpenAIClient),
        ("vllm", OpenAIClient),
        ("anthropic", AnthropicClient),
        ("google", GoogleClient),
    ):
        config = _config(api_type, base_url="https://example.test")
        client = create_provider_client(config, system_prompt="안내")
        assert type(client) is expected_class
        assert client.system_prompt == "안내"


@pytest.mark.parametrize("api_type", ["mindlogic", "timely", "retired"])
def test_model_config_rejects_removed_or_unknown_api_type(api_type):
    """@description 폐기·미지원 API 타입 공용 설정 거부 확인"""
    with pytest.raises(ValueError, match="지원하지 않는 API 타입입니다"):
        _config(api_type)


def test_openai_chat_stream_preserves_payload_text_usage_and_call_count(monkeypatch):
    """@description Chat Completions 본문·조각 연결·사용량·호출 횟수 확인"""
    calls = []

    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.api_key = kwargs["api_key"]
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create),
            )

        def create(self, **kwargs):
            calls.append((self.api_key, kwargs))
            return iter(
                [
                    _chunk("4"),
                    _chunk("4", SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7)),
                ]
            )

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    client = openai_provider.OpenAIClient(_config("openai"))
    client.system_prompt = "시스템 안내"
    result = client.send_request(_question())

    assert result.success is True
    assert result.raw_response == "44"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (5, 2, 7)
    assert len(calls) == 1
    assert calls[0][0] == "key-1"
    assert calls[0][1]["messages"] == [
        {"role": "system", "content": "시스템 안내"},
        {"role": "user", "content": [{"type": "text", "text": "문항 본문"}]},
    ]
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["stream_options"] == {"include_usage": True}


def test_openai_alibaba_refusal_keeps_success_contract(monkeypatch):
    """@description Alibaba 콘텐츠 거부 성공·거부 결과 계약 유지 확인"""
    calls = []

    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.api_key = kwargs["api_key"]
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError(openai_provider.ALIBABA_CONTENT_REFUSAL_MARKER)

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = openai_provider.OpenAIClient(_config("openai")).send_request(_question())

    assert result.success is False
    assert result.answer_status == "refusal"
    assert result.provider_stop_reason == "refusal"
    assert result.raw_response == ""
    assert len(calls) == 1


def test_openai_responses_stream_uses_responses_payload(monkeypatch):
    """@description Responses API 경로 스트림 텍스트·사용량 확인"""
    calls = []

    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.api_key = kwargs["api_key"]
            self.responses = SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            calls.append(kwargs)
            return iter(
                [
                    SimpleNamespace(delta="R", usage=None, response=None),
                    SimpleNamespace(
                        delta="S",
                        usage=SimpleNamespace(
                            input_tokens=6,
                            output_tokens=4,
                            total_tokens=10,
                        ),
                        response=None,
                    ),
                ]
            )

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    config = _config("openai", model_id="gpt-5.6-sol", request_api=None)
    result = openai_provider.OpenAIClient(config).send_request(_question())

    assert result.success is True
    assert result.raw_response == "RS"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (6, 4, 10)
    assert len(calls) == 1
    assert calls[0]["stream"] is True
    assert calls[0]["input"][0]["content"] == [
        {"type": "input_text", "text": "문항 본문"},
    ]


def test_anthropic_rest_stream_preserves_payload_and_usage(monkeypatch):
    """@description Anthropic REST 스트림 헤더·본문·텍스트·토큰 확인"""
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            return iter(
                [
                    b'data: {"type":"message_start","message":{"usage":{"input_tokens":9}}}',
                    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"답"}}'.encode(),
                    b'data: {"type":"message_delta","usage":{"output_tokens":4}}',
                ]
            )

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()

    monkeypatch.setattr(anthropic_provider.requests, "post", fake_post)
    monkeypatch.setattr(anthropic_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    client = anthropic_provider.AnthropicClient(_config("anthropic"))
    client.system_prompt = "안내"
    result = client.send_request(_question())

    assert result.success is True
    assert result.raw_response == "답"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (9, 4, 13)
    assert len(calls) == 1
    headers = calls[0][1]["headers"]
    assert headers["x-api-key"] == "key-1"
    assert calls[0][1]["json"]["system"] == "안내"
    assert calls[0][1]["json"]["stream"] is True


def test_google_sdk_stream_preserves_text_usage_and_request_contents(monkeypatch):
    """@description Google google-genai SDK 경로 요청 본문·스트림 텍스트·사용량 확인"""
    calls = []
    config = _config("google", api_key="key-1")
    client = google_provider.GoogleClient.__new__(google_provider.GoogleClient)
    google_provider.APIClient.__init__(client, config)
    client.use_vertex = False
    client._current_key = "key-1"
    client.use_new_sdk = True
    client.model_id = config.model_id
    client._uploaded_files = {}

    class FakeModels:
        def generate_content_stream(self, **kwargs):
            calls.append(kwargs)
            return iter(
                [
                    SimpleNamespace(text="G", usage_metadata=None),
                    SimpleNamespace(
                        text="답",
                        usage_metadata=SimpleNamespace(
                            prompt_token_count=8,
                            candidates_token_count=3,
                            thoughts_token_count=2,
                            total_token_count=13,
                        ),
                    ),
                ]
            )

    client.client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(google_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = client.send_request(_question())

    assert result.success is True
    assert result.raw_response == "G답"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (8, 5, 13)
    assert calls == [{"model": "test-model", "contents": ["문항 본문"], "config": None}]


def test_google_thinking_level_keeps_rest_route():
    """@description thinking_level 설정 시 REST 경로 선택 계약 확인"""
    config = _config("google", api_key="key-1", thinking_level="high")
    client = google_provider.GoogleClient.__new__(google_provider.GoogleClient)
    google_provider.APIClient.__init__(client, config)
    client.use_vertex = False
    client._current_key = "key-1"
    client.use_new_sdk = True
    expected = object()
    client._send_rest_api_request = lambda question: expected

    assert client.send_request(_question()) is expected
