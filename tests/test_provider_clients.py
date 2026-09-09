"""@description 공급자 클라이언트 대표 요청·응답 계약 검증"""

from __future__ import annotations

import json
from pathlib import Path
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
        "concurrent_request_limit": 1,
        "supports_vision": True,
        "base_url": "https://example.test/v1",
    }
    values.update(overrides)
    return ModelConfig(**values)


def _question() -> Question:
    """@description 텍스트 전용 대표 문항 생성"""
    return Question(number=7, correct_answer=3, points=2, question_text="문항 본문")


def _image_question(image_path: Path) -> Question:
    """@description 이미지가 선언된 대표 문항 생성"""
    return Question(
        number=7,
        correct_answer=3,
        points=2,
        question_text="문항 본문",
        image_paths=[str(image_path)],
    )


def _chunk(
    text: str,
    usage: Any = None,
    finish_reason: str | None = None,
    refusal: str | None = None,
) -> Any:
    """@description OpenAI 호환 스트림 청크 생성"""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=text, refusal=refusal),
                finish_reason=finish_reason,
            )
        ],
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
                    SimpleNamespace(
                        type="response.output_text.delta",
                        delta="R",
                        usage=None,
                        response=None,
                    ),
                    SimpleNamespace(
                        type="response.output_text.delta",
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


def test_openai_responses_stream_excludes_reasoning_and_keeps_refusal_text(monkeypatch):
    """@description Responses API 출력 텍스트·추론 제외·거부 텍스트 보존 확인"""
    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.api_key = kwargs["api_key"]
            self.responses = SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            return iter(
                [
                    SimpleNamespace(
                        type="response.reasoning_summary_text.delta",
                        delta="추론",
                        usage=None,
                        response=None,
                    ),
                    SimpleNamespace(
                        type="response.output_text.delta",
                        delta="답",
                        usage=None,
                        response=None,
                    ),
                    SimpleNamespace(
                        type="response.refusal.delta",
                        delta="거부",
                        usage=SimpleNamespace(input_tokens=3, output_tokens=2, total_tokens=5),
                        response=None,
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        delta=None,
                        usage=None,
                        response=SimpleNamespace(status="completed"),
                    ),
                ]
            )

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = openai_provider.OpenAIClient(
        _config("openai", model_id="gpt-5.6-sol", request_api=None)
    ).send_request(_question())

    assert result.success is True
    assert result.raw_response == "답거부"
    assert result.answer_status == "refusal"
    assert result.provider_stop_reason == "refusal"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (3, 2, 5)


def test_openai_responses_stream_uses_final_only_output_text(monkeypatch):
    """@description Responses API 최종 응답만 제공되는 스트림 폴백 확인"""
    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.api_key = kwargs["api_key"]
            self.responses = SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            return iter(
                [
                    SimpleNamespace(
                        type="response.completed",
                        delta=None,
                        usage=None,
                        response=SimpleNamespace(
                            status="completed",
                            output=[SimpleNamespace(type="output_text", text="최종 답")],
                            usage=SimpleNamespace(
                                input_tokens=4,
                                output_tokens=3,
                                total_tokens=7,
                            ),
                        ),
                    )
                ]
            )

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = openai_provider.OpenAIClient(
        _config("openai", model_id="gpt-5.6-sol", request_api=None)
    ).send_request(_question())

    assert result.success is True
    assert result.raw_response == "최종 답"
    assert result.answer_status == "answered"
    assert result.provider_stop_reason == "completed"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (4, 3, 7)


def test_openai_chat_stream_preserves_refusal_text_and_stop_reason(monkeypatch):
    """@description OpenAI 호환 Chat 거부 텍스트·종료 사유 보존 확인"""
    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.api_key = kwargs["api_key"]
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            return iter(
                [
                    _chunk("", refusal="거부 "),
                    _chunk("", refusal="사유", finish_reason="refusal"),
                ]
            )

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = openai_provider.OpenAIClient(_config("grok")).send_request(_question())

    assert result.success is True
    assert result.raw_response == "거부 사유"
    assert result.answer_status == "refusal"
    assert result.provider_stop_reason == "refusal"


def test_openai_chat_stream_keeps_token_only_generation(monkeypatch):
    """@description OpenAI Chat 토큰만 있는 생성 결과의 성공 분류 확인"""
    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.api_key = kwargs["api_key"]
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            return iter(
                [
                    SimpleNamespace(
                        choices=[],
                        usage=SimpleNamespace(
                            prompt_tokens=2,
                            completion_tokens=1,
                            total_tokens=3,
                        ),
                    )
                ]
            )

    monkeypatch.setattr(openai_provider, "_ensure_openai_available", lambda: True)
    monkeypatch.setattr(openai_provider, "httpx", SimpleNamespace(Timeout=FakeTimeout))
    monkeypatch.setattr(openai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = openai_provider.OpenAIClient(_config("deepseek")).send_request(_question())

    assert result.success is True
    assert result.raw_response == ""
    assert result.answer_status == "no_answer"
    assert result.provider_stop_reason is None
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (2, 1, 3)


def test_openai_chat_and_responses_omit_images_for_text_only_model(tmp_path: Path, monkeypatch):
    """@description OpenAI Chat·Responses 경로의 이미지 생략·본문 유지 확인"""
    image_path = tmp_path / "문항.png"
    image_path.write_bytes(b"image-bytes")
    question = _image_question(image_path)
    client = openai_provider.OpenAIClient.__new__(openai_provider.OpenAIClient)
    openai_provider.APIClient.__init__(client, _config("openai", supports_vision=False))

    assert client._build_chat_content(question) == [
        {"type": "text", "text": "문항 본문"},
    ]
    assert client._build_responses_content(question) == [
        {"type": "input_text", "text": "문항 본문"},
    ]


def test_grok_chat_content_omits_images_for_text_only_model(tmp_path: Path):
    """@description Grok Chat 호환 경로의 이미지 생략·본문 유지 확인"""
    image_path = tmp_path / "문항.png"
    image_path.write_bytes(b"image-bytes")
    client = openai_provider.OpenAIClient.__new__(openai_provider.OpenAIClient)
    openai_provider.APIClient.__init__(client, _config("grok", supports_vision=False))

    assert client._build_chat_content(_image_question(image_path)) == [
        {"type": "text", "text": "문항 본문"},
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
                    b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":4}}',
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
    assert result.answer_status == "answered"
    assert result.provider_stop_reason == "end_turn"
    assert len(calls) == 1
    headers = calls[0][1]["headers"]
    assert headers["x-api-key"] == "key-1"
    assert calls[0][1]["json"]["system"] == "안내"
    assert calls[0][1]["json"]["stream"] is True


def test_anthropic_rest_omits_images_for_text_only_model(tmp_path: Path, monkeypatch):
    """@description Anthropic 요청 본문의 이미지 생략·본문 유지 확인"""
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            return iter([b'data: {"type":"message_start","message":{"usage":{"input_tokens":1}}}'])

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()

    image_path = tmp_path / "문항.png"
    image_path.write_bytes(b"image-bytes")
    monkeypatch.setattr(anthropic_provider.requests, "post", fake_post)
    monkeypatch.setattr(anthropic_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = anthropic_provider.AnthropicClient(
        _config("anthropic", supports_vision=False)
    ).send_request(_image_question(image_path))

    assert result.success is True
    assert calls[0][1]["json"]["messages"][0]["content"] == [
        {"type": "text", "text": "문항 본문"},
    ]


def test_anthropic_rest_preserves_refusal_text_and_stop_reason(monkeypatch):
    """@description Anthropic 거부 텍스트·종료 사유 보존 확인"""
    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            return iter(
                [
                    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"거부 사유"}}'.encode(),
                    'data: {"type":"message_delta","delta":{"stop_reason":"refusal"},"usage":{"output_tokens":2}}'.encode(),
                ]
            )

    monkeypatch.setattr(anthropic_provider.requests, "post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(anthropic_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = anthropic_provider.AnthropicClient(_config("anthropic")).send_request(_question())

    assert result.success is True
    assert result.raw_response == "거부 사유"
    assert result.answer_status == "refusal"
    assert result.provider_stop_reason == "refusal"


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
                        candidates=[SimpleNamespace(finish_reason="STOP")],
                    ),
                ]
            )

    client.client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(google_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = client.send_request(_question())

    assert result.success is True
    assert result.raw_response == "G답"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (8, 5, 13)
    assert result.answer_status == "answered"
    assert result.provider_stop_reason == "STOP"
    assert calls == [{"model": "test-model", "contents": ["문항 본문"], "config": None}]


def test_google_sdk_omits_images_for_text_only_model(tmp_path: Path, monkeypatch):
    """@description Google SDK 요청 본문의 이미지 생략·본문 유지 확인"""
    calls = []
    config = _config("google", api_key="key-1", supports_vision=False)
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
            return iter([SimpleNamespace(text="답", usage_metadata=None)])

    image_path = tmp_path / "문항.png"
    image_path.write_bytes(b"image-bytes")
    client.client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(google_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    result = client.send_request(_image_question(image_path))

    assert result.success is True
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


@pytest.mark.parametrize("wire_format", ["array", "sse"])
def test_google_rest_filters_thought_parts_and_captures_stop_reason(
    wire_format: str,
    monkeypatch,
):
    """@description Google REST 배열·SSE의 추론 조각 제외·종료 사유 보존 확인"""
    chunk = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "추론", "thought": True},
                        {"text": "답"},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 4,
            "candidatesTokenCount": 2,
            "totalTokenCount": 6,
        },
    }

    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            if wire_format == "array":
                return iter([json.dumps([chunk]).encode()])
            return iter([f"data: {json.dumps(chunk)}".encode()])

    monkeypatch.setattr(google_provider.requests, "post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(google_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    config = _config("google", api_key="key-1", thinking_level="high")
    client = google_provider.GoogleClient.__new__(google_provider.GoogleClient)
    google_provider.APIClient.__init__(client, config)
    client.use_vertex = False
    client._current_key = "key-1"
    client.model_id = config.model_id
    client._uploaded_files = {}

    result = client._send_rest_api_request(_question())

    assert result.success is True
    assert result.raw_response == "답"
    assert result.answer_status == "answered"
    assert result.provider_stop_reason == "STOP"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (4, 2, 6)


def test_google_rest_preserves_refusal_text_and_stop_reason(monkeypatch):
    """@description Google REST 거부 텍스트·종료 사유 보존 확인"""
    chunk = {
        "candidates": [
            {
                "content": {"parts": [{"text": "거부 안내"}]},
                "finishReason": "SAFETY",
            }
        ],
        "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 2},
    }

    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            return iter([f"data: {json.dumps(chunk)}".encode()])

    monkeypatch.setattr(google_provider.requests, "post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(google_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    config = _config("google", api_key="key-1", thinking_level="high")
    client = google_provider.GoogleClient.__new__(google_provider.GoogleClient)
    google_provider.APIClient.__init__(client, config)
    client.use_vertex = False
    client._current_key = "key-1"
    client.model_id = config.model_id
    client._uploaded_files = {}

    result = client._send_rest_api_request(_question())

    assert result.success is True
    assert result.raw_response == "거부 안내"
    assert result.answer_status == "refusal"
    assert result.provider_stop_reason == "SAFETY"


def test_google_rest_keeps_empty_refusal_text_and_block_reason(monkeypatch):
    """@description Google REST 빈 거부 본문·promptFeedback 종료 사유 보존 확인"""
    chunk = {"promptFeedback": {"blockReason": "SAFETY"}}

    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            return iter([f"data: {json.dumps(chunk)}".encode()])

    monkeypatch.setattr(google_provider.requests, "post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(google_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    config = _config("google", api_key="key-1", thinking_level="high")
    client = google_provider.GoogleClient.__new__(google_provider.GoogleClient)
    google_provider.APIClient.__init__(client, config)
    client.use_vertex = False
    client._current_key = "key-1"
    client.model_id = config.model_id
    client._uploaded_files = {}

    result = client._send_rest_api_request(_question())

    assert result.success is False
    assert result.raw_response == ""
    assert result.answer_status == "refusal"
    assert result.provider_stop_reason == "SAFETY"


def test_google_rest_keeps_token_only_generation(monkeypatch):
    """@description Google REST 토큰만 있는 생성 결과의 성공 분류 확인"""
    chunk = {
        "candidates": [{"finishReason": "STOP"}],
        "usageMetadata": {
            "promptTokenCount": 2,
            "candidatesTokenCount": 1,
            "totalTokenCount": 3,
        },
    }

    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            return iter([f"data: {json.dumps(chunk)}".encode()])

    monkeypatch.setattr(google_provider.requests, "post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(google_provider.time, "strftime", lambda *_: "2026-01-01 00:00:00")

    config = _config("google", api_key="key-1", thinking_level="high")
    client = google_provider.GoogleClient.__new__(google_provider.GoogleClient)
    google_provider.APIClient.__init__(client, config)
    client.use_vertex = False
    client._current_key = "key-1"
    client.model_id = config.model_id
    client._uploaded_files = {}

    result = client._send_rest_api_request(_question())

    assert result.success is True
    assert result.raw_response == ""
    assert result.answer_status == "no_answer"
    assert result.provider_stop_reason == "STOP"
