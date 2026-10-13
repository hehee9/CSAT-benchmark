"""@description Gemini Argon 응답·추론 수준 검사기 검증"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import requests

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "probe_gemini_argon.py"
_SCRIPT_SPEC = importlib.util.spec_from_file_location("probe_gemini_argon", _SCRIPT_PATH)
probe = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(probe)


class FakeClock:
    """@description 대기 시간을 기록하는 가상 시계"""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeResponse:
    """@description JSON 응답 본문을 흉내 내는 객체"""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else json.dumps(body)


def _config(tmp_path: Path, monkeypatch) -> Path:
    """@description 테스트 전용 단일 Google 모델 구성 생성"""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-secret-key")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "name": probe.MODEL_NAME,
                        "api_type": "google",
                        "model_id": "gemini-4-agron",
                        "api_key_env": "GOOGLE_API_KEY",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _success(text="ok"):
    """@description 일반 텍스트가 포함된 Gemini 성공 응답 생성"""
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_poll_is_start_spaced_then_tests_all_levels_and_completes(tmp_path, monkeypatch, capsys):
    """@description 최초 즉시 조회·60초 시작 간격·7단계 검사·종료 확인"""
    config_path = _config(tmp_path, monkeypatch)
    output_path = tmp_path / "logs" / "probe.json"
    clock = FakeClock()
    monkeypatch.setattr(probe.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(probe.time, "sleep", clock.sleep)
    calls = []
    starts = []

    def fake_post(url, *, headers, json, timeout):
        starts.append(clock.now)
        calls.append((url, headers, json, timeout))
        if len(calls) == 1:
            clock.now += 15
            return FakeResponse(503, {"error": {"message": "temporarily unavailable"}})
        return _success()

    monkeypatch.setattr(probe.requests, "post", fake_post)

    assert probe.main(
        ["--config", str(config_path), "--output", str(output_path), "--model-id", "gemini-4-argon"]
    ) == 0

    state = json.loads(output_path.read_text(encoding="utf-8"))
    assert state["state"] == "completed"
    assert state["model_id"] == "gemini-4-argon"
    assert state["prompt"] == "just say ok"
    assert state["poll_attempts"] == 2
    assert starts[:2] == [0, 60]
    assert clock.sleeps == [45]
    assert [call[2]["generationConfig"]["thinkingConfig"]["thinkingLevel"] for call in calls] == [
        "LOW",
        "LOW",
        "NONE",
        "MINIMAL",
        "LOW",
        "MEDIUM",
        "HIGH",
        "XHIGH",
        "MAX",
    ]
    assert all(call[0].endswith("/models/gemini-4-argon:generateContent") for call in calls)
    assert all(call[2]["contents"] == [{"role": "user", "parts": [{"text": "just say ok"}]}] for call in calls)
    assert all(call[3] == 120 for call in calls)
    assert state["summary"] == {
        "supported_levels": list(probe.THINKING_LEVELS),
        "unsupported_levels": [],
    }
    assert "GOOGLE_API_KEY" not in capsys.readouterr().out


def test_only_explicit_level_rejections_are_unsupported_and_pending_levels_retry(tmp_path, monkeypatch):
    """@description 명시적 거부만 미지원 처리하고 보류 수준만 60초 뒤 재시도"""
    config_path = _config(tmp_path, monkeypatch)
    output_path = tmp_path / "result.json"
    clock = FakeClock()
    monkeypatch.setattr(probe.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(probe.time, "sleep", clock.sleep)
    attempts = {level: 0 for level in probe.THINKING_LEVELS}
    level_starts = {level: [] for level in probe.THINKING_LEVELS}
    snapshots = []
    calls = 0
    save_state = probe._save_state

    def capture_state(path, state):
        save_state(path, state)
        snapshots.append(copy.deepcopy(state))

    monkeypatch.setattr(probe, "_save_state", capture_state)

    def fake_post(url, *, headers, json, timeout):
        nonlocal calls
        calls += 1
        level = json["generationConfig"]["thinkingConfig"]["thinkingLevel"].lower()
        if calls == 1:
            return _success()

        level_starts[level].append(clock.now)
        attempts[level] += 1
        if attempts[level] > 1:
            return _success()
        if level == "none":
            return FakeResponse(
                400,
                {"error": {"message": "Invalid value at generation_config.thinking_config.thinking_level: NONE"}},
            )
        if level == "minimal":
            return FakeResponse(400, {"error": {"message": "invalid request"}})
        if level == "low":
            return FakeResponse(404, {"error": {"message": "model not found"}})
        if level == "medium":
            raise requests.ConnectionError("connection failed for test-secret-key")
        if level == "high":
            return _success()
        if level == "xhigh":
            return FakeResponse(400, {"error": {"message": "Thinking level XHIGH is not supported for this model."}})
        return FakeResponse(200, {"promptFeedback": {"blockReason": "SAFETY"}})

    monkeypatch.setattr(probe.requests, "post", fake_post)
    assert probe.main(["--config", str(config_path), "--output", str(output_path)]) == 0

    state = json.loads(output_path.read_text(encoding="utf-8"))
    results = state["thinking_levels"]
    assert state["state"] == "completed"
    assert results["none"]["status"] == "unsupported"
    assert results["xhigh"]["status"] == "unsupported"
    assert all(results[level]["status"] == "supported" for level in ("minimal", "low", "medium", "high", "max"))
    assert results["minimal"]["attempts"] == 2
    assert results["low"]["attempts"] == 2
    assert results["medium"]["attempts"] == 2
    assert results["max"]["attempts"] == 2
    assert results["none"]["attempts"] == 1
    assert results["xhigh"]["attempts"] == 1
    for level in ("minimal", "low", "medium", "max"):
        starts = level_starts[level]
        assert len(starts) == 2
        assert starts[1] - starts[0] >= 60
    assert clock.sleeps == [60]
    failed_network_snapshot = next(
        snapshot
        for snapshot in snapshots
        if snapshot["thinking_levels"].get("medium", {}).get("error") is not None
    )
    assert "test-secret-key" not in json.dumps(failed_network_snapshot)
    assert "test-secret-key" not in output_path.read_text(encoding="utf-8")
