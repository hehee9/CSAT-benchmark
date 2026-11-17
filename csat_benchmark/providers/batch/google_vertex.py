"""@description Vertex AI Batch 전송 및 Cloud Storage 결과 수집"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote, urlparse

import requests

from ...models import ModelConfig


def enabled(config: ModelConfig) -> bool:
    """@description Vertex Batch 설정 여부 확인"""
    return bool(config.vertex_project and config.vertex_batch_gcs_uri)


def _headers(config: ModelConfig) -> dict:
    """@description ADC 액세스 토큰 및 결제 프로젝트 헤더 생성"""
    try:
        import google.auth
        import google.auth.exceptions
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise ImportError("Vertex 배치에는 google-auth가 필요합니다. pip install google-auth를 실행하세요.") from exc
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        if not credentials.valid:
            credentials.refresh(Request())
    except google.auth.exceptions.DefaultCredentialsError as exc:
        raise RuntimeError(
            "Google ADC가 필요합니다. gcloud auth application-default login을 실행하세요."
        ) from exc
    return {
        "Authorization": f"Bearer {credentials.token}",
        "x-goog-user-project": str(config.vertex_project),
    }


def _request(method: str, url: str, config: ModelConfig, **kwargs: Any) -> requests.Response:
    """@description 인증된 Vertex 또는 Cloud Storage HTTP 요청"""
    headers = _headers(config)
    headers.update(kwargs.pop("headers", {}))
    response = requests.request(method, url, headers=headers, timeout=600, **kwargs)
    if not response.ok:
        raise RuntimeError(f"Vertex Batch 요청 실패 ({response.status_code}) {method}: {response.text}")
    return response


def _gcs_parts(uri: str) -> tuple[str, str]:
    """@description Cloud Storage URI의 버킷 및 객체 경로 분리"""
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"올바른 Cloud Storage URI가 아닙니다: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def _api_root(config: ModelConfig) -> str:
    """@description Vertex 리전별 API 주소 생성"""
    location = config.vertex_location or "global"
    host = (
        "aiplatform.googleapis.com" if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return f"https://{host}/v1"


def create_batch(
    config: ModelConfig, batch_requests: Sequence[Mapping[str, Any]], batch_name: str
) -> str:
    """@description JSONL 업로드 및 Vertex Batch 작업 생성"""
    base = config.vertex_batch_gcs_uri.rstrip("/")
    input_uri = f"{base}/{batch_name}/input.jsonl"
    output_uri = f"{base}/{batch_name}/output/"
    bucket, name = _gcs_parts(input_uri)
    with tempfile.TemporaryFile(mode="w+b") as file:
        for item in batch_requests:
            body = copy.deepcopy(item["request"])
            custom_id = item["metadata"]["custom_id"]
            body.setdefault("labels", {})["csat_req"] = hashlib.sha256(
                custom_id.encode("utf-8")
            ).hexdigest()[:32]
            file.write((json.dumps({"request": body}, ensure_ascii=False) + "\n").encode("utf-8"))
        size = file.tell()
        file.seek(0)
        upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
        start = _request(
            "POST", upload_url, config,
            params={"uploadType": "resumable", "name": name},
            headers={"X-Upload-Content-Type": "application/jsonl", "X-Upload-Content-Length": str(size)},
        )
        _request(
            "PUT", start.headers["Location"], config, data=file,
            headers={"Content-Type": "application/jsonl", "Content-Length": str(size)},
        )
    location = config.vertex_location or "global"
    url = f"{_api_root(config)}/projects/{config.vertex_project}/locations/{location}/batchPredictionJobs"
    model = config.model_id.removeprefix("models/")
    payload = {
        "displayName": batch_name,
        "model": f"publishers/google/models/{model}",
        "inputConfig": {"instancesFormat": "jsonl", "gcsSource": {"uris": [input_uri]}},
        "outputConfig": {
            "predictionsFormat": "jsonl", "gcsDestination": {"outputUriPrefix": output_uri},
        },
    }
    job = _request("POST", url, config, json=payload).json()
    if not job.get("name"):
        raise RuntimeError(f"Vertex 배치 생성 응답에 name이 없습니다: {job}")
    print(f"✅ Vertex 배치 작업 생성됨: {job['name']}")
    return job["name"]


def check_batch_status(batch_id: str, config: ModelConfig) -> dict:
    """@description Vertex 배치 상태 공용 구조 변환"""
    job = _request("GET", f"{_api_root(config)}/{batch_id}", config).json()
    state = job["state"]
    stats = job.get("completionStats") or {}
    completed = int(stats.get("successfulCount", 0))
    failed = int(stats.get("failedCount", 0))
    pending = int(stats.get("incompleteCount", 0))
    total = int(stats.get("requestCount", completed + failed + pending))
    return {
        "id": job.get("name", batch_id), "status": state, "vertex_batch": True,
        "created_at": job.get("createTime"), "completed_at": job.get("endTime"),
        "failed_at": job.get("endTime") if state == "JOB_STATE_FAILED" else None,
        "request_counts": {
            "total": total, "completed": completed, "failed": failed,
            "pending": max(pending, total - completed - failed),
        },
        "raw": job,
    }


def download_results(
    batch_id: str, config: ModelConfig, output_path: Path, save_json: Callable[..., Path]
) -> Path:
    """@description Vertex 결과 JSONL 객체 전체 수집 및 JSON 저장"""
    job = _request("GET", f"{_api_root(config)}/{batch_id}", config).json()
    output_directory = (job.get("outputInfo") or {}).get("gcsOutputDirectory")
    if not output_directory:
        raise RuntimeError(f"Vertex 배치에 결과 저장 경로가 없습니다: {batch_id}")
    bucket, prefix = _gcs_parts(output_directory)
    prefix = prefix.rstrip("/") + "/"
    root = f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o"
    responses = []
    params = {"prefix": prefix}
    while True:
        page = _request("GET", root, config, params=params).json()
        for item in page.get("items", []):
            name = item["name"]
            if name.endswith(".jsonl"):
                url = f"{root}/{quote(name, safe='')}"
                contents = _request("GET", url, config, params={"alt": "media"}).text
                responses.extend(json.loads(line) for line in contents.splitlines() if line.strip())
        if not page.get("nextPageToken"):
            break
        params["pageToken"] = page["nextPageToken"]
    if not responses:
        raise RuntimeError(f"Vertex 배치 결과 JSONL이 비어 있습니다: {batch_id}")
    return save_json({"job": job, "responses": responses}, output_path)
