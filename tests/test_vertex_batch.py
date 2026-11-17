"""@description Vertex Batch 설정, 전송 및 결과 매칭 검증"""

import hashlib
import json
import builtins
from types import SimpleNamespace

import google.auth.exceptions
import pytest

from csat_benchmark.batch import ProviderBatchTransport, _is_terminal
from csat_benchmark.configuration import load_config
from csat_benchmark.models import ModelConfig
from csat_benchmark.providers.batch import google_vertex
from csat_benchmark.runs import sanitize_model_snapshot


def _config():
    return ModelConfig(name="vertex", api_type="google", api_key="key", model_id="gemini", vertex_project="project", vertex_batch_gcs_uri="gs://bucket/prefix")


def _input(number):
    return {"metadata": {"custom_id": f"question-{number}"}, "request": {"contents": [{"parts": [{"text": f"문제 {number}"}]}], "generationConfig": {"thinkingConfig": {"thinkingLevel": "HIGH"}}}}


def test_vertex_config_defaults_and_snapshot(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"vertex_batch": {"project": "p", "gcs_uri": "gs://b"}, "models": [{"name": "a", "api_type": "google"}, {"name": "b", "api_type": "google", "vertex_project": "override"}, {"name": "c", "api_type": "openai"}]}), encoding="utf-8")
    models = load_config(path, resolve_secrets=False)["models"]
    assert (models[0]["vertex_project"], models[0]["vertex_location"], models[0]["vertex_batch_gcs_uri"]) == ("p", "global", "gs://b")
    assert models[1]["vertex_project"] == "override"
    assert "vertex_project" not in models[2]
    assert not ({"vertex_project", "vertex_location", "vertex_batch_gcs_uri"} & sanitize_model_snapshot(_config()).keys())
    path.write_text(json.dumps({"models": [{"name": "a", "api_type": "google"}]}), encoding="utf-8")
    assert "vertex_project" not in load_config(path, resolve_secrets=False)["models"][0]


def test_vertex_submit_upload_and_create(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(google_vertex, "_headers", lambda config: {"Authorization": "Bearer test"})
    def request(method, url, **kwargs):
        data = kwargs.get("data")
        if data is not None:
            kwargs["data"] = data.read().decode()
        calls.append((method, url, kwargs))
        response = SimpleNamespace(ok=True, headers={}, json=lambda: {}, text="")
        if len(calls) == 1:
            response.headers["Location"] = "https://upload.example/session"
        if len(calls) == 3:
            response.json = lambda: {"name": "projects/p/locations/global/batchPredictionJobs/1"}
        return response
    monkeypatch.setattr(google_vertex.requests, "request", request)
    source = [_input(1), _input(2)]
    path = tmp_path / "input.json"
    result = ProviderBatchTransport().submit(_config(), source, input_path=path, batch_name="test", use_responses_api=False)
    assert result.endswith("/1")
    assert json.loads(path.read_text(encoding="utf-8"))["requests"] == source
    lines = [json.loads(line) for line in calls[1][2]["data"].splitlines()]
    assert lines[0]["request"]["labels"]["csat_req"] == hashlib.sha256(b"question-1").hexdigest()[:32]
    assert lines[0]["request"]["generationConfig"] == source[0]["request"]["generationConfig"]
    assert calls[0][2]["params"] == {"uploadType": "resumable", "name": "prefix/test/input.jsonl"}
    payload = calls[2][2]["json"]
    assert payload["model"] == "publishers/google/models/gemini"
    assert payload["inputConfig"]["gcsSource"]["uris"] == ["gs://bucket/prefix/test/input.jsonl"]
    assert payload["outputConfig"]["gcsDestination"]["outputUriPrefix"] == "gs://bucket/prefix/test/output/"


def test_vertex_status_and_download_pagination(tmp_path, monkeypatch):
    job = {"name": "projects/p/locations/global/batchPredictionJobs/1", "state": "JOB_STATE_SUCCEEDED", "completionStats": {"successfulCount": "2", "failedCount": "1", "incompleteCount": "0"}, "outputInfo": {"gcsOutputDirectory": "gs://bucket/prefix/output"}}
    def request(method, url, config, **kwargs):
        if "batchPredictionJobs" in url:
            return SimpleNamespace(json=lambda: job)
        params = kwargs.get("params", {})
        if params.get("alt") == "media":
            return SimpleNamespace(text=json.dumps({"request": {"contents": []}, "response": {}}) + "\n")
        if params.get("pageToken"):
            return SimpleNamespace(json=lambda: {"items": [{"name": "prefix/output/b.jsonl"}]})
        return SimpleNamespace(json=lambda: {"items": [{"name": "prefix/output/a.jsonl"}], "nextPageToken": "next"})
    monkeypatch.setattr(google_vertex, "_request", request)
    transport = ProviderBatchTransport()
    assert transport.status(job["name"], _config())["request_counts"] == {"total": 3, "completed": 2, "failed": 1, "pending": 0}
    path = transport.download(job["name"], _config(), tmp_path / "result.json")
    assert len(json.loads(path.read_text(encoding="utf-8"))["responses"]) == 2


def test_vertex_parse_labels_fallback_and_errors(tmp_path):
    source = [_input(1), _input(2), _input(3)]
    label = hashlib.sha256(b"question-2").hexdigest()[:32]
    response = {"candidates": [{"content": {"parts": [{"text": "생각", "thought": True}, {"text": "답"}]}, "finishReason": "STOP"}]}
    data = {"responses": [{"request": {"labels": {"csat_req": label}}, "response": response}, {"request": source[0]["request"], "status": "실패"}, {"request": source[2]["request"], "status": "", "response": response}]}
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    results = ProviderBatchTransport().parse(path, _config(), use_responses_api=False, input_requests=source)
    assert [item["question_number"] for item in results] == [1, 2, 3]
    assert results[0]["error_message"] == "실패"
    assert results[1]["raw_response"] == "답"
    assert results[2]["raw_response"] == "답"
    source[1]["request"] = source[0]["request"]
    with pytest.warns(UserWarning, match="1건.*다중 일치 1건"):
        remaining = ProviderBatchTransport().parse(path, _config(), use_responses_api=False, input_requests=source)
    assert [item["question_number"] for item in remaining] == [2, 3]


def test_vertex_adc_and_http_errors(monkeypatch):
    def missing_adc(**kwargs):
        raise google.auth.exceptions.DefaultCredentialsError("missing")
    import google.auth
    monkeypatch.setattr(google.auth, "default", missing_adc)
    with pytest.raises(RuntimeError, match="gcloud auth application-default login"):
        google_vertex._headers(_config())
    monkeypatch.setattr(google_vertex, "_headers", lambda config: {})
    monkeypatch.setattr(google_vertex.requests, "request", lambda *args, **kwargs: SimpleNamespace(ok=False, status_code=403, text="denied"))
    with pytest.raises(RuntimeError, match="403.*denied"):
        google_vertex._request("GET", "https://example.test", _config())


def test_vertex_missing_google_auth_has_install_message(monkeypatch):
    original_import = builtins.__import__
    def no_google_auth(name, *args, **kwargs):
        if name == "google.auth":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_google_auth)
    with pytest.raises(ImportError, match="pip install google-auth"):
        google_vertex._headers(_config())


def test_vertex_pending_and_running_are_not_terminal(monkeypatch):
    state = {"name": "projects/p/locations/global/batchPredictionJobs/1"}
    monkeypatch.setattr(google_vertex, "_request", lambda *args, **kwargs: SimpleNamespace(json=lambda: state))
    for name in ("JOB_STATE_PENDING", "JOB_STATE_QUEUED", "JOB_STATE_RUNNING"):
        state["state"] = name
        assert not _is_terminal(google_vertex.check_batch_status(state["name"], _config()))
    state["completionStats"] = {"successfulCount": "2", "failedCount": "0", "incompleteCount": "0"}
    assert not _is_terminal(google_vertex.check_batch_status(state["name"], _config()))
    state["state"] = "JOB_STATE_SUCCEEDED"
    assert _is_terminal(google_vertex.check_batch_status(state["name"], _config()))


def test_vertex_matches_null_augmented_request_and_skips_unmatched(tmp_path):
    source = [_input(1), _input(2)]
    request = {"contents": [{"role": None, "parts": [{"text": "문제 1", "fileData": None, "inlineData": {"mimeType": None, "data": None}}]}], "systemInstruction": None}
    data = {"responses": [{"request": request, "response": {"candidates": [{"content": {"parts": [{"text": "답"}]}}]}}, {"request": {"contents": [{"parts": [{"text": "다른 문제"}]}]}, "response": {}}]}
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.warns(UserWarning, match="1건.*일치 없음 1건"):
        results = ProviderBatchTransport().parse(path, _config(), use_responses_api=False, input_requests=source)
    assert [item["question_number"] for item in results] == [1]


def test_vertex_missing_output_is_runtime_error(tmp_path, monkeypatch):
    monkeypatch.setattr(google_vertex, "_request", lambda *args, **kwargs: SimpleNamespace(json=lambda: {"state": "JOB_STATE_FAILED"}))
    with pytest.raises(RuntimeError, match="결과 저장 경로"):
        google_vertex.download_results("job", _config(), tmp_path / "out.json", lambda *args: None)
