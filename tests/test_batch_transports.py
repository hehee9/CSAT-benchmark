"""@description 공급자별 Batch 전송·상태·다운로드·파싱 계약 집중 검증"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from csat_benchmark.batch import ProviderBatchTransport
from csat_benchmark.models import ModelConfig
from csat_benchmark.providers.batch import anthropic, google, openai, xai
from csat_benchmark.runs import is_technical_failure, result_is_completed


def _model_config(api_type: str) -> ModelConfig:
    """@description 모의 Batch 공급자 설정 생성"""
    return ModelConfig(
        name=f"{api_type}-모의 모델",
        api_type=api_type,
        api_key="test-key",
        model_id="fixture-model",
    )


def test_provider_transport_openai_delegates_direct_provider_functions(tmp_path: Path, monkeypatch):
    """@description OpenAI 제출·상태·다운로드 직접 함수 위임"""
    config = _model_config("openai")
    client = object()
    calls: list[tuple] = []
    monkeypatch.setattr(openai, "initialize_client", lambda model, resolve_key: client)
    monkeypatch.setattr(
        openai,
        "upload_file",
        lambda received_client, path: calls.append(("upload", received_client, path)) or "file-1",
    )
    monkeypatch.setattr(
        openai,
        "create_batch",
        lambda received_client, file_id, endpoint: calls.append(
            ("create", received_client, file_id, endpoint)
        ) or "batch-1",
    )
    monkeypatch.setattr(
        openai,
        "check_batch_status",
        lambda received_client, batch_id: calls.append(
            ("status", received_client, batch_id)
        ) or {"status": "completed"},
    )
    monkeypatch.setattr(
        openai,
        "download_results",
        lambda received_client, batch_id, output_path, resolve_path, display_path: calls.append(
            ("download", received_client, batch_id, output_path)
        ) or Path(output_path),
    )

    transport = ProviderBatchTransport()
    input_path = tmp_path / "model" / "input.jsonl"
    assert transport.submit(
        config,
        [{"custom_id": "q1"}],
        input_path=input_path,
        batch_name="fixture",
        use_responses_api=True,
    ) == "batch-1"
    assert transport.status("batch-1", config) == {"status": "completed"}
    output_path = tmp_path / "model" / "result.jsonl"
    assert transport.download("batch-1", config, output_path) == output_path
    assert calls == [
        ("upload", client, input_path),
        ("create", client, "file-1", "/v1/responses"),
        ("status", client, "batch-1"),
        ("download", client, "batch-1", str(output_path)),
    ]
    assert json.loads(input_path.read_text(encoding="utf-8"))["custom_id"] == "q1"


def test_openai_transport_preserves_submission_download_and_parsing(tmp_path: Path):
    """@description OpenAI 호환 SDK 호출 인자·다운로드 바이트·응답 파싱 확인"""
    config = _model_config("openai")
    calls: list[tuple] = []

    class Files:
        def create(self, *, file, purpose):
            calls.append(("files.create", purpose, file.read()))
            return SimpleNamespace(id="file-1")

        def content(self, file_id):
            calls.append(("files.content", file_id))
            return SimpleNamespace(content="원본 결과".encode())

    class Batches:
        def create(self, **kwargs):
            calls.append(("batches.create", kwargs))
            return SimpleNamespace(id="batch-1", status="validating")

        def retrieve(self, batch_id):
            calls.append(("batches.retrieve", batch_id))
            return SimpleNamespace(
                id=batch_id,
                status="completed",
                created_at="created",
                completed_at="completed",
                failed_at=None,
                output_file_id="file-2",
                request_counts=SimpleNamespace(total=1, completed=1, failed=0),
            )

    client = SimpleNamespace(files=Files(), batches=Batches())
    input_path = tmp_path / "input.jsonl"
    input_path.write_bytes(b"input")

    assert openai.upload_file(client, input_path) == "file-1"
    assert openai.create_batch(client, "file-1", "/v1/responses") == "batch-1"
    assert openai.check_batch_status(client, "batch-1")["request_counts"] == {
        "total": 1,
        "completed": 1,
        "failed": 0,
    }

    output_path = openai.download_results(
        client,
        "batch-1",
        "result.jsonl",
        lambda path: tmp_path / path,
        str,
    )
    assert output_path.read_bytes() == "원본 결과".encode()
    assert ("batches.create", {
        "input_file_id": "file-1",
        "endpoint": "/v1/responses",
        "completion_window": "24h",
    }) in calls

    result_path = tmp_path / "parsed.jsonl"
    result_path.write_text(
        json.dumps(
            {
                "custom_id": "run__model__target__a1__q3",
                "response": {
                    "body": {
                        "choices": [{
                            "finish_reason": "stop",
                            "message": {"content": "답변"},
                        }],
                        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                    }
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    assert openai.parse_results(result_path, config.name)[0] == {
        "request_id": "run__model__target__a1__q3",
        "question_number": 3,
        "model_name": config.name,
        "raw_response": "답변",
        "success": True,
        "error_message": None,
        "answer_status": "answered",
        "provider_stop_reason": "stop",
        "input_tokens": 4,
        "output_tokens": 2,
        "total_tokens": 6,
    }


def test_anthropic_transport_preserves_status_download_and_token_recount(tmp_path: Path):
    """@description Anthropic 상태·JSONL 저장·입력 토큰 재계산 확인"""
    config = _model_config("anthropic")

    class Entry:
        def to_dict(self):
            return {
                "custom_id": "run__model__target__a1__q2",
                "result": {
                    "type": "succeeded",
                    "message": {
                        "content": [{"type": "text", "text": "Anthropic 답변"}],
                        "stop_reason": "end_turn",
                        "usage": {"output_tokens": 3},
                    },
                },
            }

    class Messages:
        class Batches:
            def create(self, *, requests):
                return SimpleNamespace(to_dict=lambda: {"id": "anthropic-1", "processing_status": "in_progress"})

            def retrieve(self, batch_id):
                def to_dict(*, mode="python"):
                    assert mode == "json"
                    return {
                        "id": batch_id,
                        "processing_status": "ended",
                        "request_counts": {
                            "processing": 0,
                            "succeeded": 1,
                            "errored": 0,
                            "canceled": 0,
                            "expired": 0,
                        },
                    }

                return SimpleNamespace(to_dict=to_dict)

            def results(self, batch_id):
                return [Entry()]

        batches = Batches()

    client = SimpleNamespace(messages=Messages())
    assert anthropic.create_batch(client, [{"custom_id": "q2"}])["id"] == "anthropic-1"
    assert anthropic.check_batch_status(client, "anthropic-1")["request_counts"] == {
        "total": 1,
        "completed": 1,
        "failed": 0,
        "pending": 0,
        "succeeded": 1,
        "errored": 0,
        "cancelled": 0,
        "expired": 0,
    }
    output_path = anthropic.download_results(
        client,
        "anthropic-1",
        "result.jsonl",
        lambda path: tmp_path / path,
        str,
    )
    parsed = anthropic.parse_results(
        output_path,
        config.name,
        config,
        {"run__model__target__a1__q2": {"messages": [], "model": config.model_id}},
        count_input_tokens=lambda params, model: 8,
    )
    assert parsed[0]["raw_response"] == "Anthropic 답변"
    assert parsed[0]["input_tokens"] == 8
    assert parsed[0]["total_tokens"] == 11


def test_anthropic_error_result_is_retryable_but_successful_no_answer_is_complete(
    tmp_path: Path,
):
    """@description Anthropic 기술 실패 재시도·성공 no_answer 완료 판정 확인"""
    result_path = tmp_path / "result.jsonl"
    result_path.write_text(
        "\n".join(
            json.dumps(result, ensure_ascii=False)
            for result in [
                {
                    "custom_id": "run__model__target__a1__q2",
                    "result": {
                        "type": "errored",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "At least one image is too large",
                        },
                    },
                },
                {
                    "custom_id": "run__model__target__a1__q3",
                    "result": {
                        "type": "succeeded",
                        "message": {
                            "content": [],
                            "stop_reason": "end_turn",
                            "usage": {
                                "input_tokens": 11,
                                "output_tokens": 3,
                                "total_tokens": 14,
                            },
                        },
                    },
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    parsed = anthropic.parse_results(result_path, "anthropic-모의 모델")
    errored, successful_no_answer = parsed

    assert errored["success"] is False
    assert errored["answer_status"] == "technical_failure"
    assert is_technical_failure(errored)
    assert not result_is_completed(errored)

    assert successful_no_answer["success"] is True
    assert successful_no_answer["answer_status"] == "no_answer"
    assert result_is_completed(successful_no_answer)
    assert not is_technical_failure(successful_no_answer)


def test_anthropic_token_recount_uses_initialized_provider_client(monkeypatch):
    """@description 입력 토큰 재계산 시 직접 초기화 클라이언트·요청 인자 확인"""
    config = _model_config("anthropic")
    calls = []

    def count_tokens(**params):
        calls.append(("count", params))
        return SimpleNamespace(input_tokens=8)

    client = SimpleNamespace(messages=SimpleNamespace(count_tokens=count_tokens))

    def initialize(model_config, resolve_api_key):
        calls.append(("initialize", model_config.name, resolve_api_key(model_config)))
        return client

    monkeypatch.setattr(anthropic, "initialize_client", initialize)
    transport = ProviderBatchTransport()
    assert transport._count_anthropic_input_tokens({}, config) is None
    assert calls == []
    params = {"model": config.model_id, "messages": [], "max_tokens": 100}
    assert transport._count_anthropic_input_tokens(params, config) == 8
    assert transport._clients[config.name] is client
    assert calls == [
        ("initialize", config.name, "test-key"),
        ("count", {"model": config.model_id, "messages": []}),
    ]


def test_google_transport_preserves_rest_payload_status_download_and_parsing(tmp_path: Path):
    """@description Gemini REST 요청 본문·상태 집계·결과 파싱 확인"""
    config = _model_config("google")
    calls: list[tuple] = []
    payload = {
        "name": "batches/google-1",
        "state": "JOB_STATE_SUCCEEDED",
        "completionStats": {"requestCount": 1, "successfulRequestCount": 1},
    }

    def request_fn(method, url, model_config, **kwargs):
        calls.append((method, url, kwargs))
        return payload

    created = google.create_batch(config, [{"metadata": {"custom_id": "q1"}}], "fixture", request_fn)
    assert created["name"] == "batches/google-1"
    status = google.check_batch_status("batches/google-1", config, request_fn)
    assert status["request_counts"] == {"total": 1, "completed": 1, "failed": 0, "pending": 0}

    def save_json(data, path):
        output = tmp_path / path
        output.write_text(json.dumps(data), encoding="utf-8")
        return output

    output_path = google.download_results(
        "batches/google-1", config, "result.json", request_fn, save_json, str
    )
    assert json.loads(output_path.read_text(encoding="utf-8"))["name"] == "batches/google-1"
    assert calls[0][2]["json_body"]["batch"]["displayName"] == "fixture"
    result_path = tmp_path / "inline.json"
    result_path.write_text(
        json.dumps({
            "dest": {
                "inlinedResponses": [{
                    "metadata": {"custom_id": "run__model__target__a1__q4"},
                    "response": {
                        "candidates": [{
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "Gemini 답변"}]},
                        }],
                        "usageMetadata": {
                            "promptTokenCount": 5,
                            "candidatesTokenCount": 2,
                            "thoughtsTokenCount": 1,
                        },
                    },
                }]
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    parsed = google.parse_results(result_path, config.name)
    assert parsed[0]["request_id"] == "run__model__target__a1__q4"
    assert parsed[0]["raw_response"] == "Gemini 답변"
    assert parsed[0]["output_tokens"] == 3
    assert parsed[0]["total_tokens"] == 8


def test_xai_transport_preserves_chunks_pagination_status_and_errors(tmp_path: Path):
    """@description xAI 청크 제출·페이지 순회·상태 매핑·성공/실패 파싱 확인"""
    config = _model_config("grok")
    calls: list[tuple] = []
    result_pages = iter([
        {"succeeded": [], "pagination_token": "next"},
        {"succeeded": [], "failed": []},
    ])

    def request_fn(method, path, model_config, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/batches/grok-1/results":
            return next(result_pages)
        if path == "/batches/grok-1":
            return {"batch_id": "grok-1", "state": {
                "num_requests": 2,
                "num_pending": 0,
                "num_success": 1,
                "num_error": 1,
                "num_cancelled": 0,
            }}
        if path == "/batches":
            return {"batch_id": "grok-1"}
        return {}

    assert xai.create_batch(config, "fixture", request_fn)["batch_id"] == "grok-1"
    xai.add_batch_requests("grok-1", [{"id": 1}, {"id": 2}], config, request_fn, interval_seconds=0, chunk_size=1)
    assert xai.check_batch_status("grok-1", config, request_fn)["status"] == "completed"

    def save_json(data, path):
        output = tmp_path / path
        output.write_text(json.dumps(data), encoding="utf-8")
        return output

    output_path = xai.download_results("grok-1", config, "result.json", request_fn, save_json)
    assert len(json.loads(output_path.read_text(encoding="utf-8"))["pages"]) == 2
    assert calls[1][2]["json_body"] == {"batch_requests": [{"batch_request": {"id": 1}}]}

    result_path = tmp_path / "xai.json"
    result_path.write_text(json.dumps({"pages": [{
        "succeeded": [{
            "batch_request_id": "run__model__target__a1__q2",
            "response": {
                "choices": [{"finish_reason": "stop", "message": {"content": "xAI 답변"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        }],
        "failed": [{
            "batch_request_id": "run__model__target__a1__q3",
            "error": {"message": "rate limited", "type": "rate_limit"},
        }],
    }]}, ensure_ascii=False), encoding="utf-8")
    parsed = xai.parse_results(result_path, config.name)
    assert parsed[0]["request_id"] == "run__model__target__a1__q2"
    assert parsed[1]["request_id"] == "run__model__target__a1__q3"
    assert parsed[0]["raw_response"] == "xAI 답변"
    assert parsed[1]["error_details"] == {"message": "rate limited", "type": "rate_limit"}


def test_provider_transport_preserves_attempt_ids_for_same_question(tmp_path: Path):
    """@description 동일 문항 성공·실패 시도별 전체 요청 ID 보존"""
    request_ids = (
        "run__model__target__a1__q7",
        "run__model__target__a2__q7",
    )
    configs = {
        "openai": _model_config("openai"),
        "anthropic": _model_config("anthropic"),
        "google": _model_config("google"),
        "grok": _model_config("grok"),
    }
    paths = {
        "openai": tmp_path / "openai.jsonl",
        "anthropic": tmp_path / "anthropic.jsonl",
        "google": tmp_path / "google.json",
        "grok": tmp_path / "grok.json",
    }
    paths["openai"].write_text(
        "\n".join(
            [
                json.dumps({
                    "custom_id": request_ids[0],
                    "response": {"body": {
                        "choices": [{"message": {"content": "성공"}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    }},
                }, ensure_ascii=False),
                json.dumps({
                    "custom_id": request_ids[1],
                    "error": {"message": "실패"},
                }, ensure_ascii=False),
            ]
        ) + "\n",
        encoding="utf-8",
    )
    paths["anthropic"].write_text(
        "\n".join(
            [
                json.dumps({
                    "custom_id": request_ids[0],
                    "result": {"type": "succeeded", "message": {
                        "content": [{"type": "text", "text": "성공"}],
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    }},
                }, ensure_ascii=False),
                json.dumps({
                    "custom_id": request_ids[1],
                    "result": {"type": "errored", "error": {"message": "실패"}},
                }, ensure_ascii=False),
            ]
        ) + "\n",
        encoding="utf-8",
    )
    paths["google"].write_text(
        json.dumps({"dest": {"inlinedResponses": [
            {
                "metadata": {"custom_id": request_ids[0]},
                "response": {"candidates": [{"content": {"parts": [{"text": "성공"}]}}]},
            },
            {
                "metadata": {"custom_id": request_ids[1]},
                "error": {"message": "실패"},
            },
        ]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["grok"].write_text(
        json.dumps({"pages": [{
            "succeeded": [{
                "batch_request_id": request_ids[0],
                "response": {"choices": [{"message": {"content": "성공"}}]},
            }],
            "failed": [{
                "batch_request_id": request_ids[1],
                "error": {"message": "실패"},
            }],
        }]}, ensure_ascii=False),
        encoding="utf-8",
    )

    for provider, config in configs.items():
        parsed = ProviderBatchTransport().parse(
            paths[provider],
            config,
            use_responses_api=False,
            input_requests=[],
        )
        assert [record["request_id"] for record in parsed] == list(request_ids)
        assert [record["question_number"] for record in parsed] == [7, 7]
        assert [record["success"] for record in parsed] == [True, False]
