"""@description Claude 5.5 설정과 Anthropic 요청 경로 검증"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from csat_benchmark import batch as batch_module
from csat_benchmark.models import ModelConfig, Question
from csat_benchmark.providers import anthropic as anthropic_provider
from csat_benchmark.providers.requests import build_anthropic_thinking_config
from csat_benchmark.runner import _load_model_configs


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
CLAUDE_55_NAMES = (
    "Claude Opus 5.5 (high)",
    "Claude Opus 5.5",
    "Claude Sonnet 5.5 (high)",
    "Claude Sonnet 5.5",
    "Claude Haiku 5.5 (high)",
    "Claude Haiku 5.5",
)


def _load_selected_models(
    monkeypatch: pytest.MonkeyPatch,
    names: tuple[str, ...],
    *,
    resolve_secrets: bool,
):
    """@description 현재 설정의 지정 모델·인증 정보 로드"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-test-key")
    models, snapshots, _ = _load_model_configs(
        CONFIG_PATH,
        names,
        resolve_secrets=resolve_secrets,
    )
    return models, snapshots


def _question() -> Question:
    """@description Anthropic 요청 비교용 텍스트 문항 생성"""
    return Question(number=7, correct_answer=3, points=2, question_text="문항 본문")


def _claude_55_models() -> dict[str, ModelConfig]:
    """@description Claude 5.5 승인 속성 기준 모델 설정 생성"""
    specs = (
        ("Claude Opus 5.5 (high)", "claude-opus-5-5", 4, 20, 100, True, "high"),
        ("Claude Opus 5.5", "claude-opus-5-5", 4, 20, 50, False, None),
        ("Claude Sonnet 5.5 (high)", "claude-sonnet-5-5", 2, 10, 100, True, "high"),
        ("Claude Sonnet 5.5", "claude-sonnet-5-5", 2, 10, 50, False, None),
        ("Claude Haiku 5.5 (high)", "claude-haiku-5-5", 0.1, 0.5, 100, True, "high"),
        ("Claude Haiku 5.5", "claude-haiku-5-5", 0.1, 0.5, 50, False, None),
    )
    return {
        name: ModelConfig(
            name=name,
            api_type="anthropic",
            api_key="claude-test-key",
            model_id=model_id,
            max_tokens=128000,
            concurrent_request_limit=10,
            priority=priority,
            price={"input": input_price, "output": output_price},
            thinking_enabled=thinking_enabled,
            reasoning_effort=effort,
        )
        for (
            name,
            model_id,
            input_price,
            output_price,
            priority,
            thinking_enabled,
            effort,
        ) in specs
    }


@pytest.mark.skipif(not CONFIG_PATH.is_file(), reason="로컬 config.json이 없는 환경에서는 생략")
def test_claude_55_config_selection_resolves_credentials_and_preserves_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@description Claude 5.5 설정 선택·인증 정보·속성 검증"""
    models, snapshots = _load_selected_models(
        monkeypatch,
        CLAUDE_55_NAMES,
        resolve_secrets=True,
    )

    expected = {
        "Claude Opus 5.5 (high)": ("claude-opus-5-5", 4, 20, 100, True, "high"),
        "Claude Opus 5.5": ("claude-opus-5-5", 4, 20, 50, False, None),
        "Claude Sonnet 5.5 (high)": ("claude-sonnet-5-5", 2, 10, 100, True, "high"),
        "Claude Sonnet 5.5": ("claude-sonnet-5-5", 2, 10, 50, False, None),
        "Claude Haiku 5.5 (high)": ("claude-haiku-5-5", 0.1, 0.5, 100, True, "high"),
        "Claude Haiku 5.5": ("claude-haiku-5-5", 0.1, 0.5, 50, False, None),
    }
    source_records = {
        record["name"]: record
        for record in json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["models"]
    }

    assert set(models) == set(expected)
    for name, (
        model_id,
        input_price,
        output_price,
        priority,
        thinking_enabled,
        effort,
    ) in expected.items():
        config = models[name]
        assert config.api_type == "anthropic"
        assert config.model_id == model_id
        assert config.price == {"input": input_price, "output": output_price}
        assert config.max_tokens == 128000
        assert config.concurrent_request_limit == 10
        assert config.priority == priority
        assert config.api_key == "claude-test-key"
        assert config.thinking_enabled is thinking_enabled
        assert config.reasoning_effort == effort
        assert config.thinking_budget_tokens is None
        assert config.knowledge_cutoff is None
        assert config.plan_message_ko is None
        assert config.plan_message_en is None
        assert snapshots[name]["knowledge_cutoff"] is None
        assert "knowledge_cutoff" not in source_records[name]
        assert "plan_message_ko" not in source_records[name]
        assert "plan_message_en" not in source_records[name]


def test_claude_55_normal_http_payload_matches_batch_request_for_all_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@description Claude 5.5 일반·배치 요청 파라미터 일치 검증"""
    models = _claude_55_models()
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self):
            return iter(
                [
                    (
                        'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
                        '"text":"답"}}'
                    ).encode("utf-8"),
                ]
            )

    def _fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()

    monkeypatch.setattr(anthropic_provider.requests, "post", _fake_post)
    question = _question()
    system_prompt = "공통 안내"

    for name, config in models.items():
        client = anthropic_provider.AnthropicClient(config)
        client.system_prompt = system_prompt
        result = client.send_request(question)
        assert result.success is True

        normal_payload = dict(calls[-1][1]["json"])
        assert normal_payload.pop("stream") is True
        if name.endswith("(high)"):
            assert normal_payload["thinking"] == {"type": "adaptive"}
            assert normal_payload["output_config"] == {"effort": "high"}
            assert "budget_tokens" not in normal_payload["thinking"]
        else:
            assert normal_payload["thinking"] == {"type": "disabled"}
            assert "output_config" not in normal_payload
        batch_request = batch_module._base_request(
            config,
            question,
            provider="anthropic",
            use_responses_api=False,
            system_prompt=system_prompt,
        )
        assert normal_payload == batch_request["params"]

    assert len(calls) == len(CLAUDE_55_NAMES)


def test_existing_anthropic_thinking_shapes_and_fable_omission_remain_unchanged() -> None:
    """@description 기존 Claude 추론 모드·Fable 생략 동작 검증"""
    manual_budget = ModelConfig(
        name="Claude Haiku 4.5 (32K Thinking)",
        api_type="anthropic",
        api_key="test-key",
        model_id="claude-haiku-4-5-20251001",
        thinking_enabled=True,
        thinking_budget_tokens=32000,
    )
    adaptive = ModelConfig(
        name="Claude Sonnet 5 (high)",
        api_type="anthropic",
        api_key="test-key",
        model_id="claude-sonnet-5",
        thinking_enabled=True,
        reasoning_effort="high",
    )
    plain = ModelConfig(
        name="Claude Opus 5",
        api_type="anthropic",
        api_key="test-key",
        model_id="claude-opus-5",
    )
    fable_high = ModelConfig(
        name="Claude Fable 5.1 (high)",
        api_type="anthropic",
        api_key="test-key",
        model_id="claude-fable-5-1",
        thinking_enabled=True,
        reasoning_effort="high",
    )
    fable_effort_only = ModelConfig(
        name="Claude Fable 5.1 (high, no thinking)",
        api_type="anthropic",
        api_key="test-key",
        model_id="claude-fable-5-1",
        thinking_enabled=False,
        reasoning_effort="high",
    )

    assert build_anthropic_thinking_config(manual_budget) == {
        "thinking": {"type": "enabled", "budget_tokens": 32000},
    }
    assert build_anthropic_thinking_config(adaptive) == {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
    }
    assert build_anthropic_thinking_config(plain) == {
        "thinking": {"type": "disabled"},
    }
    assert build_anthropic_thinking_config(fable_high) == {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
    }
    assert build_anthropic_thinking_config(fable_effort_only) == {
        "output_config": {"effort": "high"},
    }
