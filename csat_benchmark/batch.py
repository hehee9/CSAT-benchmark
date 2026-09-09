"""@description 시험 매니페스트 기반 배치 실행·실행 기록 관리"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Sequence

from .exams import ExamManifest, ModeManifest, SectionManifest, load_exam
from .models import ModelConfig, Question
from .providers.batch import anthropic as anthropic_batch
from .providers.batch import google as google_batch
from .providers.batch import openai as openai_batch
from .providers.batch import xai as xai_batch
from .providers.requests import (
    build_anthropic_params,
    build_chat_body,
    build_google_request,
    build_responses_body,
    validate_question_media,
)
from .runner import (
    RunnerError,
    _load_model_configs,
    _merge_stored_run,
    _prepare_sections,
    _resolve_mode,
    _resolve_manifest,
    _run_path,
    select_sections,
)
from .runs import (
    RunStore,
    create_run,
    get_result,
    initialize_model_results,
    invalidate_verified_results,
    model_results_path,
    result_is_completed,
    save_run_metadata,
    verified_result_is_completed,
)


BATCH_STATE_FILE = "batch_state.json"
# 외부에서 예전 상수명을 가져오는 코드와의 호환을 위해 이름만 유지한다.
BATCH_MANIFEST_FILE = BATCH_STATE_FILE
BATCH_MANIFEST_VERSION = 2
_SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_TERMINAL_STATUSES = {
    "completed",
    "failed",
    "cancelled",
    "canceled",
    "expired",
    "ended",
    "job_state_succeeded",
    "job_state_failed",
    "job_state_cancelled",
    "job_state_expired",
    "job_state_partially_succeeded",
    "batch_state_succeeded",
    "batch_state_failed",
    "batch_state_cancelled",
    "batch_state_expired",
    "batch_state_partially_succeeded",
}


class BatchError(RuntimeError):
    """@description batch 실행 선택·저장·공급자 계약 오류"""


@dataclass(frozen=True)
class BatchSlot:
    """@description 단일 batch 요청 담당 실행 결과 슬롯"""

    request_id: str
    target: str
    subject: str
    section: str
    model_name: str
    question_number: int
    question: Question

    @property
    def identity(self) -> tuple[str, str, int]:
        """@description 실행 결과 슬롯 식별키 반환"""
        return self.target, self.model_name, self.question_number


class BatchTransport:
    """@description 공급자별 배치 작업 인터페이스"""

    def submit(
        self,
        model_config: ModelConfig,
        requests: Sequence[Mapping[str, Any]],
        *,
        input_path: Path,
        batch_name: str,
        use_responses_api: bool,
    ) -> str:
        """@description 요청 목록 공급자 제출 및 batch ID 반환"""
        raise NotImplementedError

    def create(
        self,
        model_config: ModelConfig,
        requests: Sequence[Mapping[str, Any]],
        *,
        input_path: Path,
        batch_name: str,
    ) -> str:
        """@description xAI 원격 batch 생성 및 입력 파일 저장"""
        raise NotImplementedError

    def add(
        self,
        model_config: ModelConfig,
        batch_id: str,
        requests: Sequence[Mapping[str, Any]],
        *,
        before_chunk: Callable[[Sequence[Mapping[str, Any]], int, int], None] | None = None,
        after_chunk: Callable[[Sequence[Mapping[str, Any]], int, int], None] | None = None,
    ) -> None:
        """@description xAI 원격 batch 요청 청크 추가"""
        raise NotImplementedError

    def status(self, batch_id: str, model_config: ModelConfig) -> Dict[str, Any]:
        """@description 공급자 배치 상태 → 공용 상태 매핑 변환"""
        raise NotImplementedError

    def download(self, batch_id: str, model_config: ModelConfig, output_path: Path) -> Path:
        """@description 완료 batch 원본 결과 저장 및 경로 반환"""
        raise NotImplementedError

    def parse(
        self,
        result_path: Path,
        model_config: ModelConfig,
        *,
        use_responses_api: bool,
        input_requests: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """@description 공급자 원본 결과 공용 응답 레코드 변환"""
        raise NotImplementedError


class ProviderBatchTransport(BatchTransport):
    """@description 공용 공급자 Batch API 직접 연결"""

    def __init__(self) -> None:
        self._clients: Dict[str, Any] = {}

    @staticmethod
    def _resolve_api_key(model_config: ModelConfig) -> str:
        """@description 모델 설정 기준 API 키 선택"""
        if isinstance(model_config.api_key, list):
            if not model_config.api_key:
                raise ValueError(f"API 키가 비어 있습니다: {model_config.name}")
            return model_config.api_key[0]
        return model_config.api_key

    def _client(self, model_config: ModelConfig) -> Any:
        """@description 공급자별 직접 SDK 클라이언트 초기화·재사용"""
        if model_config.name in self._clients:
            return self._clients[model_config.name]
        if model_config.api_type == "anthropic":
            client = anthropic_batch.initialize_client(model_config, self._resolve_api_key)
        elif model_config.api_type == "google":
            client = google_batch.initialize_client(model_config, self._resolve_api_key)
        elif model_config.api_type == "grok":
            client = xai_batch.initialize_client(model_config)
        else:
            client = openai_batch.initialize_client(model_config, self._resolve_api_key)
        self._clients[model_config.name] = client
        return client

    @staticmethod
    def _save_json(payload: Mapping[str, Any], output_path: str | Path) -> Path:
        """@description 공급자 입력·결과 JSON 저장"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _save_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> Path:
        """@description OpenAI 호환 Batch 입력 JSONL 저장"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def _google_request(
        self,
        method: str,
        url: str,
        model_config: ModelConfig,
        json_body: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """@description Google Batch REST 요청 위임"""
        return google_batch.request(
            method,
            url,
            model_config,
            self._resolve_api_key,
            json_body=json_body,
        )

    def _xai_request(
        self,
        method: str,
        path: str,
        model_config: ModelConfig,
        json_body: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """@description xAI Batch REST 요청 위임"""
        return xai_batch.request(
            method,
            path,
            model_config,
            self._resolve_api_key,
            json_body=json_body,
            params=params,
        )

    def submit(
        self,
        model_config: ModelConfig,
        requests: Sequence[Mapping[str, Any]],
        *,
        input_path: Path,
        batch_name: str,
        use_responses_api: bool,
    ) -> str:
        """@description 공급자별 Batch 직접 제출 및 ID 반환"""
        provider = model_config.api_type
        requests_list = [copy.deepcopy(dict(item)) for item in requests]
        if provider == "grok":
            batch_id = self.create(
                model_config,
                requests_list,
                input_path=input_path,
                batch_name=batch_name,
            )
            self.add(model_config, batch_id, requests_list)
            return batch_id

        if provider == "anthropic":
            self._save_json({"requests": requests_list}, input_path)
            batch = anthropic_batch.create_batch(self._client(model_config), requests_list)
            return str(batch["id"])

        if provider == "google":
            self._save_json({"requests": requests_list}, input_path)
            batch = google_batch.create_batch(
                model_config,
                requests_list,
                batch_name,
                self._google_request,
            )
            return str(batch["name"])

        self._save_jsonl(input_path, requests_list)
        file_id = openai_batch.upload_file(self._client(model_config), input_path)
        endpoint = "/v1/responses" if use_responses_api else "/v1/chat/completions"
        return str(openai_batch.create_batch(self._client(model_config), file_id, endpoint))

    def create(
        self,
        model_config: ModelConfig,
        requests: Sequence[Mapping[str, Any]],
        *,
        input_path: Path,
        batch_name: str,
    ) -> str:
        """@description xAI 원격 batch 생성 전 입력 저장 및 ID 반환"""
        if model_config.api_type != "grok":
            raise BatchError("create는 xAI Batch API에서만 사용할 수 있습니다.")
        requests_list = [copy.deepcopy(dict(item)) for item in requests]
        self._save_json({"batch_requests": requests_list}, input_path)
        batch = xai_batch.create_batch(model_config, batch_name, self._xai_request)
        batch_id = batch.get("batch_id") or batch.get("id")
        if not batch_id:
            raise BatchError(f"xAI 배치 생성 응답에 batch_id가 없습니다: {batch}")
        return str(batch_id)

    def add(
        self,
        model_config: ModelConfig,
        batch_id: str,
        requests: Sequence[Mapping[str, Any]],
        *,
        before_chunk: Callable[[Sequence[Mapping[str, Any]], int, int], None] | None = None,
        after_chunk: Callable[[Sequence[Mapping[str, Any]], int, int], None] | None = None,
    ) -> None:
        """@description xAI 원격 batch 요청 청크 추가 및 상태 지점 위임"""
        if model_config.api_type != "grok":
            raise BatchError("add는 xAI Batch API에서만 사용할 수 있습니다.")
        xai_batch.add_batch_requests(
            str(batch_id),
            [copy.deepcopy(dict(item)) for item in requests],
            model_config,
            self._xai_request,
            before_chunk=before_chunk,
            after_chunk=after_chunk,
        )

    def status(self, batch_id: str, model_config: ModelConfig) -> Dict[str, Any]:
        """@description 공급자별 Batch 상태 조회 위임"""
        if model_config.api_type == "grok":
            return xai_batch.check_batch_status(batch_id, model_config, self._xai_request)
        if model_config.api_type == "anthropic":
            return anthropic_batch.check_batch_status(self._client(model_config), batch_id)
        if model_config.api_type == "google":
            return google_batch.check_batch_status(batch_id, model_config, self._google_request)
        return openai_batch.check_batch_status(self._client(model_config), batch_id)

    def download(self, batch_id: str, model_config: ModelConfig, output_path: Path) -> Path:
        """@description 공급자별 Batch 결과 다운로드 위임"""
        if model_config.api_type == "grok":
            return xai_batch.download_results(
                batch_id,
                model_config,
                str(output_path),
                self._xai_request,
                self._save_json,
            )
        if model_config.api_type == "anthropic":
            return anthropic_batch.download_results(
                self._client(model_config),
                batch_id,
                str(output_path),
                Path,
                str,
            )
        if model_config.api_type == "google":
            return google_batch.download_results(
                batch_id,
                model_config,
                str(output_path),
                self._google_request,
                self._save_json,
                str,
            )
        return openai_batch.download_results(
            self._client(model_config),
            batch_id,
            str(output_path),
            Path,
            str,
        )

    def _count_anthropic_input_tokens(
        self,
        params: Dict[str, Any],
        model_config: ModelConfig,
    ) -> int | None:
        """@description Anthropic 입력 토큰 직접 재계산"""
        if "messages" not in params or "model" not in params:
            return None
        return anthropic_batch.count_request_input_tokens(
            self._client(model_config),
            params,
        )

    def parse(
        self,
        result_path: Path,
        model_config: ModelConfig,
        *,
        use_responses_api: bool,
        input_requests: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """@description 공급자 원본 결과 전체 파일 파싱"""
        provider = model_config.api_type
        if provider == "grok":
            return xai_batch.parse_results(result_path, model_config.name)
        if provider == "anthropic":
            return anthropic_batch.parse_results(
                result_path,
                model_config.name,
                model_config,
                _anthropic_params_by_id(input_requests),
                count_input_tokens=self._count_anthropic_input_tokens,
            )
        if provider == "google":
            input_custom_ids = [
                custom_id
                for request in input_requests
                for metadata in [request.get("metadata") or {}]
                for custom_id in [metadata.get("custom_id") or metadata.get("customId")]
                if isinstance(custom_id, str)
            ]
            return google_batch.parse_results(
                result_path,
                model_config.name,
                input_custom_ids,
            )
        return openai_batch.parse_results(
            result_path,
            model_config.name,
            use_responses_api,
        )


def _result_suffix(provider: str) -> str:
    """@description 공급자 원본 결과 파일 확장자 반환"""
    return ".json" if provider in {"google", "grok"} else ".jsonl"


def _input_suffix(provider: str) -> str:
    """@description 공급자 batch 입력 파일 확장자 반환"""
    return ".json" if provider in {"google", "grok", "anthropic"} else ".jsonl"


def _anthropic_params_by_id(
    requests: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """@description Anthropic 요청 목록 기준 ID별 params 매핑 생성"""
    return {
        str(request["custom_id"]): dict(request["params"])
        for request in requests
        if "custom_id" in request and isinstance(request.get("params"), Mapping)
    }


def _load_input_requests(path: Path) -> List[Mapping[str, Any]]:
    """@description 저장된 공급자 입력 요청 목록 로드"""
    if not path.is_file():
        return []
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("requests"), list):
        return payload["requests"]
    if isinstance(payload.get("batch_requests"), list):
        return payload["batch_requests"]
    return []


def _safe_id(value: str, limit: int = 24) -> str:
    """@description 공급자 파일명·작업명용 안정적 짧은 문자열 생성"""
    normalized = _SAFE_ID_PATTERN.sub("_", value).strip("._-")
    if normalized and len(normalized) <= limit:
        return normalized
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    prefix_limit = max(1, limit - len(digest) - 1)
    return f"{(normalized or 'item')[:prefix_limit]}-{digest}"


def _request_id(model_name: str, target: str, question_number: int) -> str:
    """@description 모델·target·문항 키 기반 결정론적 공급자 요청 ID 생성"""
    key = f"{model_name}\x1f{target}\x1f{question_number}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return (
        f"{_safe_id(model_name, 14)}__{_safe_id(target, 20)}__"
        f"{digest}__q{question_number}"
    )


def _set_request_id(provider: str, request: Dict[str, Any], request_id: str) -> None:
    """@description 공급자 요청 본문에 내부 요청 ID 설정"""
    if provider == "grok":
        request["chat_get_completion"]["batch_request_id"] = request_id
    elif provider == "google":
        request.setdefault("metadata", {})["custom_id"] = request_id
    else:
        request["custom_id"] = request_id


def _xai_request_ids(requests: Sequence[Mapping[str, Any]]) -> List[str]:
    """@description xAI 요청 청크의 내부 요청 ID 추출"""
    return [
        str(request["chat_get_completion"]["batch_request_id"])
        for request in requests
    ]


def _base_request(
    model_config: ModelConfig,
    question: Question,
    *,
    provider: str,
    use_responses_api: bool,
    system_prompt: str,
) -> Dict[str, Any]:
    """@description 기존 공급자 요청 생성기를 이용한 단일 batch 요청 생성"""
    if provider == "anthropic":
        return {
            "custom_id": f"q{question.number}",
            "params": build_anthropic_params(
                question,
                model_config,
                system_prompt=system_prompt,
                skip_missing=False,
            ),
        }
    if provider == "google":
        return {
            "metadata": {"custom_id": f"q{question.number}"},
            "request": build_google_request(
                question,
                model_config,
                system_prompt=system_prompt,
            ),
        }
    if provider == "grok":
        body = build_chat_body(
            question,
            model_config,
            system_prompt=system_prompt,
            skip_missing=False,
            image_url_mode="data_url",
            merge_multiple_images=False,
            extra_body_mode="top_level",
        )
        body["batch_request_id"] = f"q{question.number}"
        return {"chat_get_completion": body}

    body = (
        build_responses_body(
            question,
            model_config,
            system_prompt=system_prompt,
            image_format="data_url",
            skip_missing=False,
            extra_body_mode="top_level",
        )
        if use_responses_api
        else build_chat_body(
            question,
            model_config,
            system_prompt=system_prompt,
            skip_missing=False,
            image_url_mode="data_url",
            merge_multiple_images=False,
            extra_body_mode="top_level",
        )
    )
    return {
        "custom_id": f"q{question.number}",
        "method": "POST",
        "url": "/v1/responses" if use_responses_api else "/v1/chat/completions",
        "body": body,
    }


def _identity_key(identity: tuple[str, str, int]) -> str:
    """@description 결과 식별 튜플의 상태 매핑 키 생성"""
    return json.dumps(list(identity), ensure_ascii=False, separators=(",", ":"))


def _request_metadata(slot: BatchSlot) -> Dict[str, Any]:
    """@description 요청 ID별 결과 저장 문맥 생성"""
    return {
        "request_id": slot.request_id,
        "target": slot.target,
        "subject": slot.subject,
        "section": slot.section,
        "model_name": slot.model_name,
        "question_number": slot.question_number,
        "identity": list(slot.identity),
    }


def _slots_for_selection(
    selected_sections: Sequence[SectionManifest],
    prepared: Mapping[str, Sequence[tuple[Question, int]]],
    model_name: str,
    run: Mapping[str, Any],
    contexts: Mapping[str, Mapping[str, Any]],
    *,
    retry_failed: bool,
    index_path: Path,
) -> List[BatchSlot]:
    """@description 선택 범위에서 미실행·기술 실패 batch 슬롯 생성"""
    slots: List[BatchSlot] = []
    for section in selected_sections:
        context = contexts[section.target]
        actual_numbers = context["question_numbers"]
        for question, question_number in prepared[section.target]:
            identity = (section.target, model_name, question_number)
            previous = get_result(run, identity)
            if retry_failed:
                if verified_result_is_completed(
                    index_path,
                    model_name,
                    section.target,
                    question_number,
                    input_mode=context["input_mode"],
                    question_numbers=actual_numbers,
                ):
                    continue
                if previous is not None and result_is_completed(previous):
                    continue
            slots.append(
                BatchSlot(
                    request_id=_request_id(model_name, section.target, question_number),
                    target=section.target,
                    subject=section.subject,
                    section=section.section,
                    model_name=model_name,
                    question_number=question_number,
                    question=question,
                )
            )
    return slots


def _new_batch_state(run: Mapping[str, Any]) -> Dict[str, Any]:
    """@description 시험·mode별 현재 batch 상태 초기화"""
    return {
        "schema_version": BATCH_MANIFEST_VERSION,
        "exam_id": run["exam_id"],
        "mode": run["mode"],
        "jobs": [],
        "request_map": {},
    }


def _state_path(index_path: Path) -> Path:
    """@description 정본 색인과 같은 mode 폴더의 batch 상태 경로 반환"""
    return index_path.parent / BATCH_STATE_FILE


def _validate_batch_state(state: Mapping[str, Any], run: Mapping[str, Any]) -> None:
    """@description 현재 batch 상태의 필수 필드·시험 일치 검증"""
    if state.get("schema_version") != BATCH_MANIFEST_VERSION:
        raise BatchError("지원하지 않는 batch 상태 schema_version입니다.")
    if state.get("exam_id") != run["exam_id"] or state.get("mode") != run["mode"]:
        raise BatchError("batch 상태가 현재 시험·mode와 일치하지 않습니다.")
    if not isinstance(state.get("jobs"), list) or not isinstance(state.get("request_map"), Mapping):
        raise BatchError("batch 상태 jobs·request_map 형식이 잘못되었습니다.")
    for job in state["jobs"]:
        if not isinstance(job, Mapping):
            raise BatchError("batch 상태 job 항목은 객체여야 합니다.")
        for field_name in ("model_name", "provider", "provider_batch_id", "input_path"):
            if not isinstance(job.get(field_name), str) or not job[field_name]:
                raise BatchError(f"batch 상태 job의 {field_name}가 없습니다.")
        if not isinstance(job.get("request_map"), Mapping):
            raise BatchError("batch 상태 job request_map은 객체여야 합니다.")
        if "merged_request_ids" in job and not isinstance(job["merged_request_ids"], list):
            raise BatchError("batch 상태 job merged_request_ids는 목록이어야 합니다.")
        if "run_id" in job or "attempt" in job:
            raise BatchError("batch 상태에는 실행 ID·시도 필드를 저장할 수 없습니다.")


def _load_batch_state(index_path: Path, run: Mapping[str, Any]) -> Dict[str, Any]:
    """@description 정본 mode별 현재 batch 상태 로드"""
    path = _state_path(index_path)
    if not path.is_file():
        return _new_batch_state(run)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise BatchError(f"batch 상태가 객체가 아닙니다: {path}")
    state = copy.deepcopy(dict(payload))
    _validate_batch_state(state, run)
    return state


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    """@description batch 상태 JSON 원자적 교체 저장"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(
        f".{path.name}.{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _is_terminal(status_info: Mapping[str, Any]) -> bool:
    """@description 공급자 상태 종료 여부 확인"""
    status = str(status_info.get("status", "")).lower()
    if status in _TERMINAL_STATUSES:
        return True
    counts = status_info.get("request_counts") or {}
    pending = counts.get("pending")
    return isinstance(pending, int) and pending == 0 and status not in {"", "unknown", "in_progress"}


def _resolve_transport(
    transport: BatchTransport | None,
    transport_factory: Callable[[], BatchTransport] | None,
) -> BatchTransport:
    """@description 배치 전송 객체 선택"""
    if transport is not None and transport_factory is not None:
        raise ValueError("transport와 transport_factory는 함께 사용할 수 없습니다.")
    if transport is not None:
        return transport
    if transport_factory is not None:
        return transport_factory()
    return ProviderBatchTransport()


def _prepare_submit_context(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool,
    model_names: Sequence[str] | None,
    targets: Sequence[str] | None,
    subject: str | None,
    section: str | None,
    subjects: Sequence[str] | None,
    benchmark_all: bool,
    question_numbers: Sequence[int] | None,
    output: str | Path | None,
    output_dir: str | Path | None,
) -> Dict[str, Any]:
    """@description 제출 입력·정본 실행·선택 모델 준비"""
    manifest = _resolve_manifest(exam)
    selected_mode = _resolve_mode(manifest, None, easy=easy)
    if output is not None and output_dir is not None:
        raise RunnerError("output과 output_dir은 함께 사용할 수 없습니다.")
    index_path = _run_path(manifest, selected_mode, output=output, output_dir=output_dir)
    selected_sections = select_sections(
        manifest,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
    )
    contexts, prepared = _prepare_sections(
        manifest,
        selected_sections,
        selected_mode,
        question_numbers,
    )
    model_configs, snapshots, system_prompt = _load_model_configs(
        config_path,
        model_names,
        resolve_secrets=True,
    )
    for questions in prepared.values():
        for question, _ in questions:
            for model_config in model_configs.values():
                validate_question_media(question, model_config, batch=True)

    current_run = create_run(
        exam_id=manifest.id,
        mode=selected_mode.id,
        input_mode=selected_mode.input_mode,
        selected_targets=[item.target for item in selected_sections],
        selected_models=[snapshots[name] for name in model_configs],
        input_context=contexts,
        system_prompt=system_prompt,
    )
    if index_path.is_file():
        stored_run = RunStore.load(index_path).run
        if stored_run["exam_id"] != manifest.id or stored_run["mode"] != selected_mode.id:
            raise RunnerError("기존 정본 시험·mode가 현재 선택과 다릅니다.")
        run = _merge_stored_run(stored_run, current_run)
    else:
        run = current_run
    return {
        "exam": manifest,
        "mode": selected_mode,
        "run": run,
        "path": index_path,
        "model_configs": model_configs,
        "snapshots": snapshots,
        "system_prompt": system_prompt,
        "sections": selected_sections,
        "contexts": {context["target"]: context for context in contexts},
        "prepared": prepared,
    }


def _build_run_requests(
    model_config: ModelConfig,
    *,
    use_responses_api: bool,
    system_prompt: str,
    slots: Sequence[BatchSlot],
) -> List[Dict[str, Any]]:
    """@description 슬롯에 대응하는 기존 공급자 요청 본문 생성"""
    requests: List[Dict[str, Any]] = []
    for slot in slots:
        request = _base_request(
            model_config,
            slot.question,
            provider=model_config.api_type,
            use_responses_api=use_responses_api,
            system_prompt=system_prompt,
        )
        _set_request_id(model_config.api_type, request, slot.request_id)
        requests.append(request)
    return requests


def _scope_records(
    slots: Sequence[BatchSlot],
    contexts: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """@description batch job 선택 범위의 target별 요약 생성"""
    targets = {slot.target for slot in slots}
    return [
        {
            "target": target,
            "subject": contexts[target]["subject"],
            "section": contexts[target]["section"],
            "input_mode": contexts[target]["input_mode"],
            "question_numbers": list(contexts[target]["question_numbers"]),
        }
        for target in (context["target"] for context in contexts.values())
        if target in targets
    ]


def _job_identities(job: Mapping[str, Any]) -> set[tuple[str, str, int]]:
    """@description batch job request map의 결과 식별키 집합 반환"""
    identities = set()
    for metadata in job["request_map"].values():
        identity = metadata.get("identity")
        if isinstance(identity, list) and len(identity) == 3:
            identities.add((identity[0], identity[1], identity[2]))
    return identities


def _job_is_active(job: Mapping[str, Any]) -> bool:
    """@description 아직 결과를 회수하지 않은 비종료 batch 여부 반환"""
    if job.get("downloaded") is True:
        return False
    return not _is_terminal(job.get("status_info") or {"status": job.get("status", "")})


def _scope_targets(
    manifest: ExamManifest,
    mode: ModeManifest,
    *,
    targets: Sequence[str] | None,
    subject: str | None,
    section: str | None,
    subjects: Sequence[str] | None,
    benchmark_all: bool,
    question_numbers: Sequence[int] | None,
) -> set[str]:
    """@description 조회·재시도 선택자의 target 집합 반환"""
    if question_numbers and mode.input_mode != "question":
        raise RunnerError("--question-numbers는 문항별 input_mode에서만 사용할 수 있습니다.")
    return {
        item.target
        for item in select_sections(
            manifest,
            targets=targets,
            subject=subject,
            section=section,
            subjects=subjects,
            benchmark_all=benchmark_all,
        )
    }


def _job_matches(
    job: Mapping[str, Any],
    *,
    selected_models: set[str],
    selected_targets: set[str],
    question_numbers: Sequence[int] | None,
) -> bool:
    """@description 저장 job이 현재 모델·scope 선택에 포함되는지 판정"""
    if selected_models and job["model_name"] not in selected_models:
        return False
    request_map = job["request_map"]
    for metadata in request_map.values():
        if metadata["target"] not in selected_targets:
            continue
        if question_numbers and metadata["question_number"] not in set(question_numbers):
            continue
        return True
    return False


def _operation_context(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool,
    model_names: Sequence[str] | None,
    targets: Sequence[str] | None,
    subject: str | None,
    section: str | None,
    subjects: Sequence[str] | None,
    benchmark_all: bool,
    question_numbers: Sequence[int] | None,
    output: str | Path | None,
    output_dir: str | Path | None,
) -> Dict[str, Any]:
    """@description 기존 정본·batch 상태·조회 선택 준비"""
    manifest = _resolve_manifest(exam)
    selected_mode = _resolve_mode(manifest, None, easy=easy)
    if output is not None and output_dir is not None:
        raise RunnerError("output과 output_dir은 함께 사용할 수 없습니다.")
    index_path = _run_path(manifest, selected_mode, output=output, output_dir=output_dir)
    selected_targets = _scope_targets(
        manifest,
        selected_mode,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
    )
    if not index_path.is_file():
        raise BatchError(f"시험·mode의 정본 결과가 없습니다: {index_path}")
    run = RunStore.load(index_path).run
    if run["exam_id"] != manifest.id or run["mode"] != selected_mode.id:
        raise RunnerError("조회할 정본의 시험·mode가 현재 선택과 다릅니다.")
    state = _load_batch_state(index_path, run)
    state_models = list(dict.fromkeys(job["model_name"] for job in state["jobs"]))
    selected_model_names = list(model_names) if model_names is not None else state_models
    if not selected_model_names and index_path.is_file():
        selected_model_names = [model["name"] for model in run["selected_models"]]
    model_configs: Dict[str, ModelConfig] = {}
    if selected_model_names:
        model_configs, _, _ = _load_model_configs(
            config_path,
            selected_model_names,
            resolve_secrets=True,
        )
    return {
        "exam": manifest,
        "mode": selected_mode,
        "run": run,
        "path": index_path,
        "state": state,
        "selected_models": set(selected_model_names),
        "selected_targets": selected_targets,
        "model_configs": model_configs,
    }


def _save_run_before_batch(
    context: Mapping[str, Any],
    slots: Sequence[BatchSlot],
) -> RunStore:
    """@description 정본 metadata와 신규 raw sidecar를 요청 전에 준비"""
    run = context["run"]
    path = context["path"]
    model_names = sorted({slot.model_name for slot in slots})
    if model_names:
        initialize_model_results(run, path, model_names)
    store = RunStore(run, path)
    # 선택 target·model union은 raw sidecar를 다시 쓰지 않고 metadata만 갱신한다.
    save_run_metadata(run, path)
    return store


def _record_batch_result(
    run: MutableMapping[str, Any],
    store: RunStore,
    result: Mapping[str, Any],
    request_map: Mapping[str, Mapping[str, Any]],
    state: Mapping[str, Any],
    provider_batch_id: str,
) -> bool:
    """@description 최신 request map에 속한 공급자 결과만 정본에 upsert"""
    request_id = result.get("request_id")
    metadata = request_map.get(request_id)
    if metadata is None:
        return False
    current = state["request_map"].get(request_id)
    if current is None or current.get("provider_batch_id") != provider_batch_id:
        return False
    record = {
        "target": metadata["target"],
        "subject": metadata["subject"],
        "section": metadata["section"],
        "model_name": metadata["model_name"],
        "question_number": metadata["question_number"],
        "raw_response": result.get("raw_response", ""),
        "timestamp": result.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "success": result.get("success") is True,
        "error_message": result.get("error_message"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "total_tokens": result.get("total_tokens"),
        "answer_status": result.get("answer_status"),
        "provider_stop_reason": result.get("provider_stop_reason"),
        "error_details": result.get("error_details"),
    }
    store.upsert(record)
    return True


def submit_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool = False,
    model_names: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
    question_numbers: Sequence[int] | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    retry_failed: bool = False,
    use_responses_api: bool | None = None,
    transport: BatchTransport | None = None,
    transport_factory: Callable[[], BatchTransport] | None = None,
) -> Dict[str, Any]:
    """@description 선택 범위의 단일 생성 요청을 provider batch로 제출"""
    context = _prepare_submit_context(
        exam,
        config_path=config_path,
        easy=easy,
        model_names=model_names,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
        output=output,
        output_dir=output_dir,
    )
    run = context["run"]
    state = _load_batch_state(context["path"], run)
    selected_transport = _resolve_transport(transport, transport_factory)
    selected_protocol = bool(use_responses_api)

    all_slots: List[BatchSlot] = []
    slots_by_model: Dict[str, List[BatchSlot]] = {}
    for model_name, model_config in context["model_configs"].items():
        if not model_config.batch_supported:
            raise BatchError(f"{model_name} 모델은 현재 Batch API를 지원하지 않습니다.")
        slots = _slots_for_selection(
            context["sections"],
            context["prepared"],
            model_name,
            run,
            context["contexts"],
            retry_failed=retry_failed,
            index_path=context["path"],
        )
        if slots:
            slots_by_model[model_name] = slots
            all_slots.extend(slots)

    selected_keys = {slot.identity for slot in all_slots}
    active_overlap = {
        identity
        for job in state["jobs"]
        if _job_is_active(job)
        for identity in _job_identities(job)
        if identity in selected_keys
    }
    if active_overlap:
        raise BatchError(
            "선택한 target·모델·문항 중 이미 처리 중인 batch가 있습니다: "
            + ", ".join(map(str, sorted(active_overlap)))
        )

    store = _save_run_before_batch(context, all_slots)
    for slot in all_slots:
        invalidate_verified_results(
            context["path"],
            slot.model_name,
            slot.target,
            slot.question_number,
            input_mode=context["contexts"][slot.target]["input_mode"],
            question_numbers=context["contexts"][slot.target]["question_numbers"],
        )

    for model_name, slots in slots_by_model.items():
        model_config = context["model_configs"][model_name]
        requests = _build_run_requests(
            model_config,
            use_responses_api=selected_protocol,
            system_prompt=context["system_prompt"],
            slots=slots,
        )
        key_digest = hashlib.sha256(
            "\x1f".join(sorted(_identity_key(slot.identity) for slot in slots)).encode("utf-8")
        ).hexdigest()[:12]
        model_dir = model_results_path(context["path"], model_name).parent
        model_dir.mkdir(parents=True, exist_ok=True)
        input_path = model_dir / (
            f"batch-input-{_safe_id(model_name, 20)}-{key_digest}"
            f"{_input_suffix(model_config.api_type)}"
        )
        batch_name = f"{context['exam'].id}-{context['mode'].id}-{_safe_id(model_name, 20)}-{key_digest}"
        request_map = {
            slot.request_id: _request_metadata(slot)
            for slot in slots
        }
        if model_config.api_type == "grok":
            provider_batch_id = selected_transport.create(
                model_config,
                requests,
                input_path=input_path,
                batch_name=batch_name,
            )
        else:
            provider_batch_id = selected_transport.submit(
                model_config,
                requests,
                input_path=input_path,
                batch_name=batch_name,
                use_responses_api=selected_protocol,
            )
        job = {
            "model_name": model_name,
            "provider": model_config.api_type,
            "scopes": _scope_records(slots, context["contexts"]),
            "provider_batch_id": str(provider_batch_id),
            "request_ids": [slot.request_id for slot in slots],
            "request_map": request_map,
            "status": "submitted",
            "status_info": {},
            "downloaded": False,
            "merged_request_ids": [],
            "input_path": str(input_path),
            "use_responses_api": selected_protocol,
        }
        if model_config.api_type == "grok":
            job.update(
                {
                    "submission_status": "created",
                    "submitted_request_ids": [],
                    "in_flight_request_ids": [],
                    "submission_progress": {
                        "submitted": 0,
                        "total": len(requests),
                        "chunks_submitted": 0,
                        "chunks_total": (
                            len(requests) + xai_batch.XAI_BATCH_REQUEST_CHUNK_SIZE - 1
                        )
                        // xai_batch.XAI_BATCH_REQUEST_CHUNK_SIZE,
                    },
                }
            )
        state["jobs"].append(job)
        for request_id, metadata in request_map.items():
            current = dict(metadata)
            current["provider_batch_id"] = str(provider_batch_id)
            state["request_map"][request_id] = current
        _save_json(_state_path(context["path"]), state)

        if model_config.api_type == "grok":
            def _before_chunk(
                chunk: Sequence[Mapping[str, Any]],
                chunk_number: int,
                total_chunks: int,
            ) -> None:
                """@description xAI 청크 전송 전 in-flight 요청 ID 저장"""
                job["submission_status"] = "in_progress"
                job["in_flight_request_ids"] = _xai_request_ids(chunk)
                job["submission_progress"]["chunks_total"] = total_chunks
                _save_json(_state_path(context["path"]), state)

            def _after_chunk(
                chunk: Sequence[Mapping[str, Any]],
                chunk_number: int,
                total_chunks: int,
            ) -> None:
                """@description xAI 청크 승인 후 제출 ID·진행률 저장"""
                confirmed = set(job["submitted_request_ids"])
                confirmed.update(_xai_request_ids(chunk))
                job["submitted_request_ids"] = [
                    request_id
                    for request_id in job["request_ids"]
                    if request_id in confirmed
                ]
                job["in_flight_request_ids"] = []
                job["submission_progress"] = {
                    "submitted": len(job["submitted_request_ids"]),
                    "total": len(job["request_ids"]),
                    "chunks_submitted": chunk_number,
                    "chunks_total": total_chunks,
                }
                _save_json(_state_path(context["path"]), state)

            try:
                selected_transport.add(
                    model_config,
                    str(provider_batch_id),
                    requests,
                    before_chunk=_before_chunk,
                    after_chunk=_after_chunk,
                )
            except (RuntimeError, TimeoutError):
                job["submission_status"] = "failed"
                _save_json(_state_path(context["path"]), state)
                raise
            job["submission_status"] = "complete"
            _save_json(_state_path(context["path"]), state)

    _save_json(_state_path(context["path"]), state)
    result = {
        "run": store.run,
        "mode": context["mode"].id,
        "path": str(context["path"]),
        "batch_state": state,
        "batch_manifest": state,
        "submitted": len(all_slots),
    }
    return result


def _selected_operation_jobs(
    context: Mapping[str, Any],
) -> List[MutableMapping[str, Any]]:
    """@description 조회 선택자에 포함된 batch job 목록 반환"""
    return [
        job
        for job in context["state"]["jobs"]
        if _job_matches(
            job,
            selected_models=context["selected_models"],
            selected_targets=context["selected_targets"],
            question_numbers=context["question_numbers"],
        )
    ]


def _selected_request_ids(
    job: Mapping[str, Any],
    context: Mapping[str, Any],
) -> set[str]:
    """@description 현재 조회 범위에서 아직 병합하지 않은 요청 ID 반환"""
    selected_models = context["selected_models"]
    selected_targets = context["selected_targets"]
    question_numbers = set(context["question_numbers"] or [])
    merged = set(job.get("merged_request_ids", []))
    selected: set[str] = set()
    for request_id, metadata in job["request_map"].items():
        if request_id in merged:
            continue
        if selected_models and job["model_name"] not in selected_models:
            continue
        if metadata["target"] not in selected_targets:
            continue
        if question_numbers and metadata["question_number"] not in question_numbers:
            continue
        selected.add(request_id)
    return selected


def _load_operation_context_with_filters(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool,
    model_names: Sequence[str] | None,
    targets: Sequence[str] | None,
    subject: str | None,
    section: str | None,
    subjects: Sequence[str] | None,
    benchmark_all: bool,
    question_numbers: Sequence[int] | None,
    output: str | Path | None,
    output_dir: str | Path | None,
) -> Dict[str, Any]:
    """@description 조회·대기·다운로드용 선택 문맥 완성"""
    context = _operation_context(
        exam,
        config_path=config_path,
        easy=easy,
        model_names=model_names,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
        output=output,
        output_dir=output_dir,
    )
    context["question_numbers"] = question_numbers
    return context


def status_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool = False,
    model_names: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
    question_numbers: Sequence[int] | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    transport: BatchTransport | None = None,
    transport_factory: Callable[[], BatchTransport] | None = None,
) -> Dict[str, Any]:
    """@description 선택 범위의 provider batch 상태 조회"""
    context = _load_operation_context_with_filters(
        exam,
        config_path=config_path,
        easy=easy,
        model_names=model_names,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
        output=output,
        output_dir=output_dir,
    )
    selected_transport = _resolve_transport(transport, transport_factory)
    statuses: List[Dict[str, Any]] = []
    for job in _selected_operation_jobs(context):
        model_config = context["model_configs"][job["model_name"]]
        status_info = selected_transport.status(job["provider_batch_id"], model_config)
        job["status"] = status_info.get("status")
        job["status_info"] = status_info
        statuses.append(
            dict(
                status_info,
                provider_batch_id=job["provider_batch_id"],
                model_name=job["model_name"],
            )
        )
    _save_json(_state_path(context["path"]), context["state"])
    return {
        "run": context["run"],
        "mode": context["mode"].id,
        "path": str(context["path"]),
        "statuses": statuses,
        "batch_state": context["state"],
        "batch_manifest": context["state"],
    }


def _print_wait_banner(provider: str, batch_id: str, check_interval: int) -> None:
    """@description 공급자별 batch 완료 대기 시작 문구 출력"""
    if provider == "anthropic":
        print(f"⏳ Anthropic 배치 완료 대기 중... (ID: {batch_id})")
        print(f"   {check_interval}초마다 상태를 확인합니다.")
        return
    if provider == "grok":
        print(f"⏳ xAI 배치 완료 대기 중... (ID: {batch_id})")
        if check_interval == 300:
            print(f"   {check_interval}초(5분)마다 상태를 확인합니다.")
        else:
            print(f"   {check_interval}초마다 상태를 확인합니다.")
        return
    if provider == "google":
        print(f"⏳ Gemini 배치 완료 대기 중... (ID: {batch_id})")
        print(f"   {check_interval}초마다 상태를 확인합니다.")
        return
    print(f"⏳ 배치 작업 완료 대기 중... (ID: {batch_id})")
    print(f"   {check_interval}초마다 상태를 확인합니다.")


def _report_batch_progress(
    job: Mapping[str, Any],
    status_info: Mapping[str, Any],
) -> None:
    """@description 이전 상태 대비 완료 문항 증가분 출력"""
    counts = status_info.get("request_counts") or {}
    previous_status_info = job.get("status_info") or {}
    previous_counts = previous_status_info.get("request_counts") or {}
    current_completed = counts.get("completed", 0) or 0
    previous_completed = previous_counts.get("completed", 0) or 0
    total = counts.get("total", 0) or len(job["request_map"])

    if current_completed > previous_completed:
        progressed = current_completed - previous_completed
        print(
            f"\n📈 진행 업데이트: {job['provider_batch_id']} | +{progressed}개 | "
            f"누적 {current_completed}/{total}"
        )


def _print_wait_status(
    provider: str,
    status_info: Mapping[str, Any],
    *,
    terminal: bool,
) -> None:
    """@description 공급자별 batch 상태·처리량 문구 출력"""
    status = status_info["status"]
    counts = status_info["request_counts"]
    if provider == "grok":
        print(
            f"   상태: {status} | 성공: {counts.get('succeeded', 0)} "
            f"| 실패: {counts['failed']} | 대기: {counts.get('pending', 0)} "
            f"| 총합: {counts['completed']}/{counts['total']}"
        )
        return
    if provider == "anthropic":
        print(
            f"\r   상태: {status} | 성공: {counts.get('succeeded', 0)} "
            f"| 실패: {counts['failed']} | 대기: {counts.get('pending', 0)} "
            f"| 총합: {counts['completed']}/{counts['total']}",
            end="",
        )
    elif provider == "google":
        print(
            f"\r   상태: {status} | 완료: {counts['completed']}/{counts['total']} "
            f"| 실패: {counts['failed']} | 대기: {counts.get('pending', 0)}",
            end="",
        )
    else:
        print(
            f"\r   상태: {status} | 완료: {counts['completed']}/{counts['total']} "
            f"| 실패: {counts['failed']}",
            end="",
        )
    if terminal:
        print()


def wait_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool = False,
    model_names: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
    question_numbers: Sequence[int] | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    check_interval: int = 60,
    download: bool = True,
    transport: BatchTransport | None = None,
    transport_factory: Callable[[], BatchTransport] | None = None,
) -> Dict[str, Any]:
    """@description 선택 batch 완료 대기 및 선택적 결과 다운로드"""
    if check_interval < 0:
        raise ValueError("check_interval은 0 이상이어야 합니다.")
    context = _load_operation_context_with_filters(
        exam,
        config_path=config_path,
        easy=easy,
        model_names=model_names,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
        output=output,
        output_dir=output_dir,
    )
    selected_transport = _resolve_transport(transport, transport_factory)
    statuses: List[Dict[str, Any]] = []
    announced_batch_ids: set[str] = set()
    while True:
        pending = False
        statuses = []
        for job in _selected_operation_jobs(context):
            if job.get("downloaded"):
                continue
            model_config = context["model_configs"][job["model_name"]]
            batch_id = job["provider_batch_id"]
            if batch_id not in announced_batch_ids:
                _print_wait_banner(model_config.api_type, batch_id, check_interval)
                announced_batch_ids.add(batch_id)
            status_info = selected_transport.status(job["provider_batch_id"], model_config)
            _report_batch_progress(job, status_info)
            terminal = _is_terminal(status_info)
            _print_wait_status(model_config.api_type, status_info, terminal=terminal)
            job["status"] = status_info.get("status")
            job["status_info"] = status_info
            statuses.append(
                dict(
                    status_info,
                    provider_batch_id=job["provider_batch_id"],
                    model_name=job["model_name"],
                )
            )
            pending = pending or not terminal
        _save_json(_state_path(context["path"]), context["state"])
        if not pending:
            break
        time.sleep(check_interval)
    if download:
        return download_exam(
            exam,
            config_path=config_path,
            easy=easy,
            model_names=model_names,
            targets=targets,
            subject=subject,
            section=section,
            subjects=subjects,
            benchmark_all=benchmark_all,
            question_numbers=question_numbers,
            output=output,
            output_dir=output_dir,
            transport=selected_transport,
        )
    return {
        "run": context["run"],
        "mode": context["mode"].id,
        "path": str(context["path"]),
        "statuses": statuses,
        "batch_state": context["state"],
        "batch_manifest": context["state"],
    }


def download_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool = False,
    model_names: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
    question_numbers: Sequence[int] | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    transport: BatchTransport | None = None,
    transport_factory: Callable[[], BatchTransport] | None = None,
) -> Dict[str, Any]:
    """@description 종료 provider batch 결과를 최신 정본 key에 다운로드·병합"""
    context = _load_operation_context_with_filters(
        exam,
        config_path=config_path,
        easy=easy,
        model_names=model_names,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
        output=output,
        output_dir=output_dir,
    )
    selected_transport = _resolve_transport(transport, transport_factory)
    store = RunStore(context["run"], context["path"])
    downloaded = 0
    saved_results = 0
    for job in _selected_operation_jobs(context):
        if job.get("downloaded"):
            continue
        selected_request_ids = _selected_request_ids(job, context)
        if not selected_request_ids:
            continue
        model_config = context["model_configs"][job["model_name"]]
        status_info = selected_transport.status(job["provider_batch_id"], model_config)
        job["status"] = status_info.get("status")
        job["status_info"] = status_info
        if not _is_terminal(status_info):
            continue
        model_dir = model_results_path(context["path"], model_config.name).parent
        model_dir.mkdir(parents=True, exist_ok=True)
        raw_path = Path(job.get("raw_path") or (model_dir / (
            f"batch-raw-{_safe_id(job['provider_batch_id'], 40)}"
            f"{_result_suffix(model_config.api_type)}"
        )))
        if raw_path.is_file():
            downloaded_path = raw_path
        else:
            try:
                downloaded_path = selected_transport.download(
                    job["provider_batch_id"],
                    model_config,
                    raw_path,
                )
            except RuntimeError as error:
                status_name = str(status_info.get("status", "")).lower()
                if status_name not in {
                    "failed",
                    "cancelled",
                    "canceled",
                    "expired",
                    "job_state_failed",
                    "batch_state_failed",
                }:
                    raise
                job["downloaded"] = True
                job["download_error"] = str(error)
                downloaded += 1
                _save_json(_state_path(context["path"]), context["state"])
                continue
            downloaded += 1
            job["raw_path"] = str(downloaded_path)
        input_requests = _load_input_requests(Path(job["input_path"]))
        parsed = selected_transport.parse(
            Path(downloaded_path),
            model_config,
            use_responses_api=bool(job.get("use_responses_api")),
            input_requests=input_requests,
        )
        merged_request_ids = set(job.get("merged_request_ids", []))
        for result in parsed:
            request_id = result.get("request_id")
            if request_id not in selected_request_ids:
                continue
            if _record_batch_result(
                context["run"],
                store,
                result,
                job["request_map"],
                context["state"],
                job["provider_batch_id"],
            ):
                saved_results += 1
            merged_request_ids.add(request_id)
        job["merged_request_ids"] = [
            request_id
            for request_id in job["request_ids"]
            if request_id in merged_request_ids
        ]
        job["downloaded"] = set(job["request_ids"]).issubset(merged_request_ids)
        job["status"] = status_info.get("status")
        _save_json(_state_path(context["path"]), context["state"])
    _save_json(_state_path(context["path"]), context["state"])
    return {
        "run": store.run,
        "mode": context["mode"].id,
        "path": str(context["path"]),
        "batch_state": context["state"],
        "batch_manifest": context["state"],
        "downloaded": downloaded,
        "saved_results": saved_results,
    }


def retry_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    easy: bool = False,
    model_names: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
    question_numbers: Sequence[int] | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    use_responses_api: bool | None = None,
    transport: BatchTransport | None = None,
    transport_factory: Callable[[], BatchTransport] | None = None,
) -> Dict[str, Any]:
    """@description 종료 batch 회수 후 누락·기술 실패 key만 재제출"""
    selected_transport = _resolve_transport(transport, transport_factory)
    downloaded = download_exam(
        exam,
        config_path=config_path,
        easy=easy,
        model_names=model_names,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
        output=output,
        output_dir=output_dir,
        transport=selected_transport,
    )
    submitted = submit_exam(
        exam,
        config_path=config_path,
        easy=easy,
        model_names=model_names,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
        question_numbers=question_numbers,
        output=output,
        output_dir=output_dir,
        retry_failed=True,
        use_responses_api=use_responses_api,
        transport=selected_transport,
    )
    submitted["downloaded_before_retry"] = downloaded
    return submitted


def _build_parser() -> argparse.ArgumentParser:
    """@description 시험 batch CLI 인자 파서 생성"""
    parser = argparse.ArgumentParser(
        description="시험 매니페스트 기반 Batch 실행기",
        allow_abbrev=False,
    )
    parser.add_argument("action", nargs="?", choices=("submit", "status", "wait", "download", "retry"))
    parser.add_argument("--action", dest="action_option", choices=("submit", "status", "wait", "download", "retry"))
    parser.add_argument("--exam", required=True, help="시험 ID 또는 매니페스트 JSON 경로")
    parser.add_argument("--config", default="config.json", help="모델 설정 경로")
    parser.add_argument("--models", nargs="+", help="실행 모델 이름")
    parser.add_argument("--targets", nargs="+", help="시험 target 목록")
    parser.add_argument("--subjects", nargs="+", help="과목 또는 탐구 영역 목록")
    parser.add_argument("--subject")
    parser.add_argument("--section")
    parser.add_argument("--question-numbers", nargs="+", type=int)
    parser.add_argument("--benchmark-all", action="store_true")
    parser.add_argument("--easy", action="store_true", help="문항별 쉬움 실행")
    parser.add_argument("--output")
    parser.add_argument("--output-dir")
    parser.add_argument("--responses-api", action="store_true", default=None)
    parser.add_argument("--check-interval", type=int, default=60)
    parser.add_argument("--no-wait", action="store_true", help="제출 후 완료 대기 생략")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    return parser


def batch_main(argv: Sequence[str] | None = None) -> int:
    """@description --exam 기준 batch 작업 실행 및 결과 요약 출력"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if (args.subject is None) != (args.section is None):
        parser.error("--subject와 --section은 함께 지정해야 합니다.")
    action_flags = [
        name
        for name, enabled in (
            ("submit", args.submit),
            ("status", args.status),
            ("wait", args.wait),
            ("download", args.download),
            ("retry", args.retry or args.retry_failed),
        )
        if enabled
    ]
    action = args.action_option or args.action or (action_flags[0] if action_flags else "submit")
    if len(set(action_flags)) > 1 or (
        args.action and action_flags and args.action != action_flags[0]
    ) or (
        args.action_option and action_flags and args.action_option != action_flags[0]
    ) or (args.action and args.action_option and args.action != args.action_option):
        parser.error("batch 작업은 submit·status·wait·download·retry 중 하나만 선택해야 합니다.")
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        current = (Path.cwd() / config_path).resolve()
        config_path = current if current.is_file() else (Path(__file__).resolve().parents[1] / config_path).resolve()
    common = {
        "config_path": config_path,
        "easy": args.easy,
        "model_names": args.models,
        "targets": args.targets,
        "subject": args.subject,
        "section": args.section,
        "subjects": args.subjects,
        "benchmark_all": args.benchmark_all,
        "question_numbers": args.question_numbers,
        "output": args.output,
        "output_dir": args.output_dir,
    }
    try:
        project_root = Path(__file__).resolve().parents[1]
        manifest_path = Path(args.exam).expanduser()
        exam_root = manifest_path.resolve().parent if manifest_path.is_file() else project_root
        exam = load_exam(args.exam, project_root=exam_root)
        if action == "submit":
            result = submit_exam(
                exam,
                **common,
                retry_failed=args.retry_failed,
                use_responses_api=args.responses_api,
            )
        elif action == "status":
            result = status_exam(exam, **common)
        elif action == "wait":
            result = wait_exam(exam, **common, check_interval=args.check_interval, download=True)
        elif action == "download":
            result = download_exam(exam, **common)
        else:
            result = retry_exam(exam, **common, use_responses_api=args.responses_api)
        if action in {"submit", "retry"} and not args.no_wait:
            summary = result
            waited = wait_exam(
                exam,
                **common,
                check_interval=args.check_interval,
                download=True,
            )
            result = {**summary, **waited}
    except (OSError, ValueError, RunnerError, BatchError) as error:
        print(f"오류: {error}")
        return 2
    print(f"mode: {result['mode']}")
    print(f"결과: {result['path']}")
    if "submitted" in result:
        print(f"제출 슬롯: {result['submitted']}")
    if "saved_results" in result:
        print(f"저장 생성: {result['saved_results']}")
    return 0


# 공개 API 이름을 짧게 사용할 수 있도록 별칭을 제공한다.
submit_batch = submit_exam
check_batch_status = status_exam
wait_for_batches = wait_exam
download_batches = download_exam
retry_batches = retry_exam


__all__ = [
    "BATCH_MANIFEST_FILE",
    "BATCH_STATE_FILE",
    "BatchError",
    "BatchSlot",
    "BatchTransport",
    "ProviderBatchTransport",
    "batch_main",
    "check_batch_status",
    "download_batches",
    "download_exam",
    "retry_batches",
    "retry_exam",
    "status_exam",
    "submit_batch",
    "submit_exam",
    "wait_exam",
    "wait_for_batches",
]


if __name__ == "__main__":
    raise SystemExit(batch_main())
