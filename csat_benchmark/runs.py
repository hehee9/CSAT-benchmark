"""@description 개별 벤치마크 실행의 정본 저장 형식·저장소 함수"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, MutableMapping, Sequence

from .exams import ExamManifest
from .models import EMPTY_RESPONSE_ERROR


RUN_SCHEMA_VERSION = 3
RUN_RESULT_FILE = "results.json"
VERIFIED_RESULT_FILE = "verified.json"
_MODEL_DIRECTORY_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MODEL_DIRECTORY_MAX_LENGTH = 48
_MODEL_DIRECTORY_PREFIX = "model-"
_CREDENTIAL_FIELDS = {"api_key", "vertex_key", "api_key_env", "vertex_key_env"}
_RUN_STORAGE_LOCK = threading.RLock()


def utc_now() -> str:
    """@description 현재 시각 기준 실행 파일 저장용 ISO 8601 문자열 반환"""
    return datetime.now(timezone.utc).isoformat()


def sanitize_model_snapshot(model: Any) -> Dict[str, Any]:
    """@description 모델 설정 인증 정보·환경 변수명 제거"""
    if is_dataclass(model):
        snapshot = asdict(model)
    elif isinstance(model, Mapping):
        snapshot = copy.deepcopy(dict(model))
    else:
        raise TypeError("모델 설정은 매핑 또는 자료 클래스여야 합니다.")
    for field_name in _CREDENTIAL_FIELDS:
        snapshot.pop(field_name, None)
    return snapshot


def _require_non_empty_string(value: Any, field_name: str) -> str:
    """@description 필수 문자열 필드 검증"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}은 비어 있지 않은 문자열이어야 합니다.")
    return value


def _model_directory_name(model_name: str) -> str:
    """@description 모델명 기반 안정적 저장 디렉터리명 계산"""
    model_name = _require_non_empty_string(model_name, "모델명")
    readable_name = unicodedata.normalize("NFKC", model_name)
    readable_name = _MODEL_DIRECTORY_INVALID_CHARS.sub("_", readable_name)
    readable_name = re.sub(r"\s+", "_", readable_name)
    readable_name = readable_name.strip(" .")
    if not readable_name:
        readable_name = "unnamed"
    readable_name = readable_name[:_MODEL_DIRECTORY_MAX_LENGTH].rstrip(" .")
    if not readable_name:
        readable_name = "unnamed"
    digest = hashlib.sha256(model_name.encode("utf-8")).hexdigest()[:12]
    return f"{_MODEL_DIRECTORY_PREFIX}{readable_name}-{digest}"


def canonical_results_path(exam: ExamManifest | str | Path, mode: str) -> Path:
    """@description 시험·mode 기준 정본 실행 색인 경로 반환"""
    if isinstance(exam, ExamManifest):
        results_root = exam.results_root
    else:
        results_root = Path(exam).expanduser().resolve()
    mode = _require_non_empty_string(mode, "mode")
    root = results_root.resolve()
    mode_path = (root / mode).resolve()
    try:
        mode_path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"mode가 결과 루트를 벗어납니다: {mode}") from error
    return mode_path / RUN_RESULT_FILE


def model_results_path(raw_index_path: str | Path, model_name: str) -> Path:
    """@description 정본 색인 기준 모델별 원본 결과 경로 계산"""
    resolved_index_path = Path(raw_index_path).expanduser().resolve()
    return (
        resolved_index_path.parent
        / "models"
        / _model_directory_name(model_name)
        / RUN_RESULT_FILE
    )


def model_verified_path(raw_index_path: str | Path, model_name: str) -> Path:
    """@description 정본 색인 기준 모델별 검증 결과 경로 계산"""
    return model_results_path(raw_index_path, model_name).with_name(VERIFIED_RESULT_FILE)


def _validate_model_results_mapping(
    run: Mapping[str, Any], model_names: Sequence[str]
) -> None:
    """@description 모델별 결과 상대 경로 매핑 검증"""
    model_results = run.get("model_results")
    if not isinstance(model_results, Mapping):
        raise ValueError("실행 model_results는 객체여야 합니다.")
    if set(model_results) != set(model_names):
        raise ValueError("실행 model_results가 선택 모델과 일치하지 않습니다.")
    for model_name in model_names:
        relative_path = model_results[model_name]
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("실행 model_results 경로는 비어 있지 않은 문자열이어야 합니다.")
        if "\\" in relative_path:
            raise ValueError("실행 model_results 경로는 슬래시 구분 상대 경로여야 합니다.")
        parsed_path = PurePosixPath(relative_path)
        if parsed_path.is_absolute() or ".." in parsed_path.parts:
            raise ValueError("실행 model_results 경로는 안전한 상대 경로여야 합니다.")


def result_identity(result: Mapping[str, Any]) -> tuple[str, str, int]:
    """@description target·모델·문항 번호 기준 결과 고유 키 반환"""
    if not isinstance(result, Mapping):
        raise TypeError("결과는 매핑이어야 합니다.")
    target = _require_non_empty_string(result.get("target"), "결과 target")
    model_name = _require_non_empty_string(result.get("model_name"), "결과 model_name")
    question_number = result.get("question_number")
    if (
        isinstance(question_number, bool)
        or not isinstance(question_number, int)
        or question_number < 0
    ):
        raise ValueError("결과 question_number는 0 이상의 정수여야 합니다.")
    return target, model_name, question_number


def result_is_completed(result: Mapping[str, Any]) -> bool:
    """@description API 생성 완료 여부 판정"""
    if result.get("success") is True:
        return True
    status = result.get("answer_status")
    if (
        result.get("error_message") == EMPTY_RESPONSE_ERROR
        and not result.get("raw_response")
        and not any(
            isinstance(result.get(field_name), (int, float))
            and not isinstance(result.get(field_name), bool)
            and result.get(field_name) > 0
            for field_name in ("input_tokens", "output_tokens", "total_tokens")
        )
    ):
        return False
    if status in {"refusal", "no_answer", "unanswered"}:
        return True
    if status in {"answer_extraction_failed", "answer_parse_failed"}:
        return bool(result.get("raw_response"))
    return False


def result_is_eligible(result: Mapping[str, Any]) -> bool:
    """@description 채점·후속 내보내기 대상 생성 결과 판정"""
    return result_is_completed(result)


def is_technical_failure(result: Mapping[str, Any]) -> bool:
    """@description 전송·제공자 실패 기준 재시도 결과 판정"""
    return not result_is_completed(result)


def _validate_result(result: Mapping[str, Any]) -> None:
    """@description 저장 결과 레코드 응답 필드 검증"""
    result_identity(result)
    if "attempt" in result:
        raise ValueError("정본 결과에는 attempt를 저장할 수 없습니다.")
    for field_name in ("subject", "section", "timestamp"):
        _require_non_empty_string(result.get(field_name), f"결과 {field_name}")
    if not isinstance(result.get("raw_response"), str):
        raise ValueError("결과 raw_response는 문자열이어야 합니다.")
    if not isinstance(result.get("success"), bool):
        raise ValueError("결과 success는 boolean이어야 합니다.")
    if result.get("error_details") is not None and not isinstance(
        result["error_details"], Mapping
    ):
        raise ValueError("결과 error_details는 객체 또는 null이어야 합니다.")


def _validate_run(run: Mapping[str, Any], *, require_results: bool = True) -> None:
    """@description 정본 실행 문서 저장 계약 검증"""
    if not isinstance(run, Mapping):
        raise TypeError("실행 문서는 매핑이어야 합니다.")
    if run.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ValueError(f"지원하지 않는 run schema_version입니다: {run.get('schema_version')}")
    for field_name in ("exam_id", "mode", "input_mode", "created_at", "updated_at"):
        _require_non_empty_string(run.get(field_name), f"실행 {field_name}")
    if "run_id" in run or "attempts_expected" in run:
        raise ValueError("정본 실행 문서에는 run_id·attempts_expected를 저장할 수 없습니다.")
    if run["input_mode"] not in {"question", "section"}:
        raise ValueError(f"지원하지 않는 실행 input_mode입니다: {run['input_mode']}")
    if "system_prompt" in run and not isinstance(run["system_prompt"], str):
        raise ValueError("실행 system_prompt는 문자열이어야 합니다.")

    targets = run.get("selected_targets")
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(target, str) or not target.strip() for target in targets)
        or len(targets) != len(set(targets))
    ):
        raise ValueError("실행 selected_targets는 중복 없는 문자열 목록이어야 합니다.")
    models = run.get("selected_models")
    if (
        not isinstance(models, list)
        or not models
        or any(not isinstance(model, Mapping) for model in models)
    ):
        raise ValueError("실행 selected_models는 하나 이상의 객체 목록이어야 합니다.")
    model_names = [model.get("name") for model in models]
    if any(not isinstance(name, str) or not name.strip() for name in model_names):
        raise ValueError("실행 selected_models의 name은 필수 문자열입니다.")
    if len(model_names) != len(set(model_names)):
        raise ValueError("실행 selected_models의 name이 중복됩니다.")
    if any(set(model) & _CREDENTIAL_FIELDS for model in models):
        raise ValueError("실행 selected_models에 인증 정보가 남아 있습니다.")
    context = run.get("input_context", [])
    if not isinstance(context, list):
        raise ValueError("실행 input_context는 목록이어야 합니다.")
    if "model_results" in run:
        _validate_model_results_mapping(run, model_names)
    if not require_results:
        if "results" in run:
            raise ValueError("실행 메타데이터에 results가 포함되어 있습니다.")
        return
    results = run.get("results")
    if not isinstance(results, list):
        raise ValueError("실행 results는 목록이어야 합니다.")
    seen: set[tuple[str, str, int]] = set()
    target_set = set(targets)
    model_name_set = set(model_names)
    for result in results:
        if not isinstance(result, Mapping):
            raise ValueError("실행 결과 항목은 객체여야 합니다.")
        _validate_result(result)
        if result["target"] not in target_set:
            raise ValueError(f"실행에 없는 target 결과입니다: {result['target']}")
        if result["model_name"] not in model_name_set:
            raise ValueError(f"실행에 없는 model 결과입니다: {result['model_name']}")
        if run["input_mode"] == "section" and result["question_number"] != 0:
            raise ValueError("section 실행의 결과 question_number는 0이어야 합니다.")
        if run["input_mode"] == "question" and result["question_number"] < 1:
            raise ValueError("question 실행의 결과 question_number는 양수여야 합니다.")
        identity = result_identity(result)
        if identity in seen:
            raise ValueError(f"실행 결과 identity가 중복됩니다: {identity}")
        seen.add(identity)


def create_run(
    *,
    exam_id: str,
    mode: str,
    input_mode: str,
    selected_targets: Sequence[str],
    selected_models: Sequence[Any],
    input_context: Sequence[Mapping[str, Any]] | None = None,
    system_prompt: str = "",
    created_at: str | None = None,
) -> Dict[str, Any]:
    """@description 정본 실행 문서 생성 및 모델 인증 정보 제거"""
    exam_id = _require_non_empty_string(exam_id, "exam_id")
    mode = _require_non_empty_string(mode, "mode")
    input_mode = _require_non_empty_string(input_mode, "input_mode")
    normalized_targets = list(selected_targets)
    normalized_models = [sanitize_model_snapshot(model) for model in selected_models]
    timestamp = created_at or utc_now()
    run = {
        "schema_version": RUN_SCHEMA_VERSION,
        "exam_id": exam_id,
        "mode": mode,
        "input_mode": input_mode,
        "created_at": timestamp,
        "updated_at": timestamp,
        "selected_targets": normalized_targets,
        "selected_models": normalized_models,
        "system_prompt": system_prompt,
        "input_context": copy.deepcopy(list(input_context or [])),
        "results": [],
    }
    _validate_run(run)
    return run


def _model_results_mapping(run: Mapping[str, Any], run_path: Path) -> Dict[str, str]:
    """@description 모델별 결과 상대 경로 매핑 생성"""
    return {
        model["name"]: model_results_path(run_path, model["name"])
        .relative_to(run_path.parent)
        .as_posix()
        for model in run["selected_models"]
    }


def _results_by_model(
    run: Mapping[str, Any],
) -> Dict[str, list[Dict[str, Any]]]:
    """@description 실행 결과 모델별 분리"""
    grouped = {model["name"]: [] for model in run["selected_models"]}
    for result in run["results"]:
        grouped[result["model_name"]].append(copy.deepcopy(dict(result)))
    return grouped


def _validate_model_sidecar(
    sidecar: Mapping[str, Any],
    run: Mapping[str, Any],
    model_name: str,
) -> None:
    """@description 모델별 원본 결과 파일 저장 계약 검증"""
    if not isinstance(sidecar, Mapping):
        raise ValueError("모델 결과 파일은 객체여야 합니다.")
    if sidecar.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ValueError(
            f"지원하지 않는 model results schema_version입니다: {sidecar.get('schema_version')}"
        )
    if sidecar.get("exam_id") != run["exam_id"]:
        raise ValueError(f"모델 결과 exam_id가 실행과 다릅니다: {model_name}")
    if sidecar.get("mode") != run["mode"]:
        raise ValueError(f"모델 결과 mode가 실행과 다릅니다: {model_name}")
    if sidecar.get("model_name") != model_name:
        raise ValueError(f"모델 결과 model_name이 경로와 다릅니다: {model_name}")
    results = sidecar.get("results")
    if not isinstance(results, list):
        raise ValueError(f"모델 결과 results가 목록이 아닙니다: {model_name}")
    target_set = set(run["selected_targets"])
    seen: set[tuple[str, str, int]] = set()
    for result in results:
        if not isinstance(result, Mapping):
            raise ValueError(f"모델 결과 항목이 객체가 아닙니다: {model_name}")
        _validate_result(result)
        if result["model_name"] != model_name:
            raise ValueError(f"모델 결과 항목 model_name이 sidecar와 다릅니다: {model_name}")
        if result["target"] not in target_set:
            raise ValueError(f"실행에 없는 target 모델 결과입니다: {result['target']}")
        if run["input_mode"] == "section" and result["question_number"] != 0:
            raise ValueError("section 실행의 결과 question_number는 0이어야 합니다.")
        if run["input_mode"] == "question" and result["question_number"] < 1:
            raise ValueError("question 실행의 결과 question_number는 양수여야 합니다.")
        identity = result_identity(result)
        if identity in seen:
            raise ValueError(f"모델 결과 identity가 중복됩니다: {identity}")
        seen.add(identity)


def _read_json(path: Path) -> Any:
    """@description UTF-8 JSON 파일 로드"""
    with path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def _write_json_atomically(path: Path, payload: Mapping[str, Any]) -> None:
    """@description 임시 파일 교체 방식 JSON 원자적 저장"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _load_canonical_run(run_path: Path, metadata: Mapping[str, Any]) -> Dict[str, Any]:
    """@description 정본 메타데이터·모델별 원본 결과 조립"""
    if metadata.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ValueError("정본 실행 메타데이터 schema_version이 아닙니다.")
    _validate_run(metadata, require_results=False)
    loaded = copy.deepcopy(dict(metadata))
    model_names = [model["name"] for model in loaded["selected_models"]]
    expected_mapping = _model_results_mapping(loaded, run_path)
    if loaded["model_results"] != expected_mapping:
        raise ValueError("실행 model_results 경로가 저장 규약과 다릅니다.")
    combined_results: list[Dict[str, Any]] = []
    for model_name in model_names:
        sidecar_path = model_results_path(run_path, model_name)
        if not sidecar_path.is_file():
            # verified-only migration에만 원본 없는 모델을 허용한다.
            if not model_verified_path(run_path, model_name).is_file():
                raise FileNotFoundError(f"모델 결과 파일을 찾을 수 없습니다: {sidecar_path}")
            continue
        sidecar = _read_json(sidecar_path)
        _validate_model_sidecar(sidecar, loaded, model_name)
        combined_results.extend(copy.deepcopy(sidecar["results"]))
    loaded.pop("model_results", None)
    loaded["results"] = combined_results
    _validate_run(loaded)
    return loaded


def load_run(path: str | Path) -> Dict[str, Any]:
    """@description 정본 실행 색인 로드 및 저장 계약 검증"""
    run_path = Path(path).expanduser().resolve()
    if not run_path.is_file():
        raise FileNotFoundError(f"실행 결과 파일을 찾을 수 없습니다: {run_path}")
    run = _read_json(run_path)
    if not isinstance(run, Mapping):
        raise ValueError("실행 결과 파일은 객체여야 합니다.")
    if run.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ValueError(f"지원하지 않는 run schema_version입니다: {run.get('schema_version')}")
    return _load_canonical_run(run_path, run)


def save_run(run: Mapping[str, Any], path: str | Path) -> Path:
    """@description 정본 메타데이터·모델별 원본 결과 원자적 저장"""
    with _RUN_STORAGE_LOCK:
        _validate_run(run)
        run_path = Path(path).expanduser().resolve()
        payload = copy.deepcopy(dict(run))
        payload["updated_at"] = utc_now()
        _validate_run(payload)
        grouped_results = _results_by_model(payload)
        model_results = _model_results_mapping(payload, run_path)
        for model_name in model_results:
            sidecar = {
                "schema_version": RUN_SCHEMA_VERSION,
                "exam_id": payload["exam_id"],
                "mode": payload["mode"],
                "model_name": model_name,
                "results": grouped_results[model_name],
            }
            _validate_model_sidecar(sidecar, payload, model_name)
            _write_json_atomically(model_results_path(run_path, model_name), sidecar)
        common = copy.deepcopy(payload)
        common.pop("results", None)
        common["model_results"] = model_results
        _validate_run(common, require_results=False)
        _write_json_atomically(run_path, common)
        if isinstance(run, MutableMapping):
            run["updated_at"] = payload["updated_at"]
        return run_path


def save_run_metadata(run: Mapping[str, Any], path: str | Path) -> Path:
    """@description 모델별 원본을 건드리지 않고 정본 메타데이터 원자적 저장"""
    with _RUN_STORAGE_LOCK:
        _validate_run(run)
        run_path = Path(path).expanduser().resolve()
        payload = copy.deepcopy(dict(run))
        payload["updated_at"] = utc_now()
        common = copy.deepcopy(payload)
        common.pop("results", None)
        common["model_results"] = _model_results_mapping(payload, run_path)
        _validate_run(common, require_results=False)
        _write_json_atomically(run_path, common)
        if isinstance(run, MutableMapping):
            run["updated_at"] = payload["updated_at"]
        return run_path


def initialize_model_results(
    run: Mapping[str, Any],
    path: str | Path,
    model_names: Sequence[str],
) -> Path:
    """@description 신규 raw 모델의 빈 sidecar 선행 초기화"""
    with _RUN_STORAGE_LOCK:
        _validate_run(run)
        run_path = Path(path).expanduser().resolve()
        known_models = {model["name"] for model in run["selected_models"]}
        requested_models = list(dict.fromkeys(model_names))
        if any(model_name not in known_models for model_name in requested_models):
            raise ValueError("초기화할 모델이 정본 selected_models에 없습니다.")
        for model_name in requested_models:
            model_path = model_results_path(run_path, model_name)
            if model_path.is_file():
                continue
            sidecar = {
                "schema_version": RUN_SCHEMA_VERSION,
                "exam_id": run["exam_id"],
                "mode": run["mode"],
                "model_name": model_name,
                "results": [],
            }
            _validate_model_sidecar(sidecar, run, model_name)
            _write_json_atomically(model_path, sidecar)
        return run_path


def upsert_result(
    run: MutableMapping[str, Any],
    result: Mapping[str, Any],
    *,
    path: str | Path | None = None,
) -> Dict[str, Any]:
    """@description target·모델·문항 번호 결과 교체 및 즉시 저장"""
    with _RUN_STORAGE_LOCK:
        _validate_run(run)
        normalized_result = copy.deepcopy(dict(result))
        _validate_result(normalized_result)
        identity = result_identity(normalized_result)
        results = run["results"]
        for index, existing in enumerate(results):
            if result_identity(existing) == identity:
                results[index] = normalized_result
                break
        else:
            results.append(normalized_result)
        _validate_run(run)
        if path is not None:
            run_path = Path(path).expanduser().resolve()
            if not run_path.exists():
                save_run(run, run_path)
            else:
                _save_upsert(run, run_path, normalized_result["model_name"])
        return normalized_result


def _save_upsert(run: Mapping[str, Any], run_path: Path, model_name: str) -> None:
    """@description 변경 모델 원본·공통 메타데이터 단독 저장"""
    existing = load_run(run_path)
    if existing["exam_id"] != run["exam_id"] or existing["mode"] != run["mode"]:
        raise ValueError("기존 정본 시험·mode가 현재 실행과 다릅니다.")
    grouped_results = _results_by_model(run)
    sidecar = {
        "schema_version": RUN_SCHEMA_VERSION,
        "exam_id": run["exam_id"],
        "mode": run["mode"],
        "model_name": model_name,
        "results": grouped_results[model_name],
    }
    _validate_model_sidecar(sidecar, run, model_name)
    _write_json_atomically(model_results_path(run_path, model_name), sidecar)
    common = copy.deepcopy(dict(run))
    common.pop("results", None)
    common["updated_at"] = utc_now()
    common["model_results"] = _model_results_mapping(run, run_path)
    _validate_run(common, require_results=False)
    _write_json_atomically(run_path, common)
    if isinstance(run, MutableMapping):
        run["updated_at"] = common["updated_at"]


def get_result(
    run: Mapping[str, Any],
    identity: tuple[str, str, int],
) -> Mapping[str, Any] | None:
    """@description 실행 기록 내 지정 식별키 결과 조회"""
    for result in run["results"]:
        if result_identity(result) == identity:
            return result
    return None


def eligible_results(run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """@description 완료 생성 결과를 입력 순서로 반환"""
    _validate_run(run)
    return [result for result in run["results"] if result_is_eligible(result)]


def _verified_envelope(path: Path) -> Mapping[str, Any] | None:
    """@description 모델별 검증 envelope 로드"""
    if not path.is_file():
        return None
    envelope = _read_json(path)
    if not isinstance(envelope, Mapping):
        raise ValueError(f"검증 결과 파일은 객체여야 합니다: {path}")
    if not isinstance(envelope.get("results"), list):
        raise ValueError(f"검증 결과 results가 목록이 아닙니다: {path}")
    return envelope


def _validate_verified_identity(
    envelope: Mapping[str, Any],
    raw_index_path: str | Path,
    model_name: str,
) -> None:
    """@description verified envelope의 모델·정본 시험·mode 일치 확인"""
    if envelope.get("model_name") != model_name:
        raise ValueError(f"검증 결과 model_name이 경로와 다릅니다: {model_name}")
    index_path = Path(raw_index_path).expanduser().resolve()
    if not index_path.is_file():
        return
    metadata = _read_json(index_path)
    if not isinstance(metadata, Mapping):
        raise ValueError(f"실행 메타데이터는 객체여야 합니다: {index_path}")
    for field_name in ("exam_id", "mode"):
        if envelope.get(field_name) != metadata.get(field_name):
            raise ValueError(f"검증 결과 {field_name}가 실행과 다릅니다: {model_name}")


def verified_completed_keys(
    raw_index_path: str | Path,
    model_name: str,
) -> set[tuple[str, str, int]]:
    """@description 모델별 verified envelope의 완료 결과 키 반환"""
    envelope = _verified_envelope(model_verified_path(raw_index_path, model_name))
    if envelope is None:
        return set()
    _validate_verified_identity(envelope, raw_index_path, model_name)
    completed: set[tuple[str, str, int]] = set()
    for result in envelope["results"]:
        if not isinstance(result, Mapping) or result.get("complete") is not True:
            continue
        if result.get("model_name", model_name) != model_name:
            continue
        completed.add(result_identity(result))
    return completed


def verified_result_is_completed(
    raw_index_path: str | Path,
    model_name: str,
    target: str,
    question_number: int,
    *,
    input_mode: str,
    question_numbers: Sequence[int] | None = None,
) -> bool:
    """@description raw 부재 시 verified 완료 범위 판정"""
    completed = verified_completed_keys(raw_index_path, model_name)
    if input_mode == "question":
        return (target, model_name, question_number) in completed
    if input_mode != "section":
        raise ValueError(f"지원하지 않는 input_mode입니다: {input_mode}")
    expected = set(question_numbers or [])
    return bool(expected) and all((target, model_name, number) in completed for number in expected)


def invalidate_verified_results(
    raw_index_path: str | Path,
    model_name: str,
    target: str,
    question_number: int,
    *,
    input_mode: str,
    question_numbers: Sequence[int] | None = None,
) -> bool:
    """@description 원본 재생성 대상 verified 결과 무효화"""
    verified_path = model_verified_path(raw_index_path, model_name)
    envelope = _verified_envelope(verified_path)
    if envelope is None:
        return False
    _validate_verified_identity(envelope, raw_index_path, model_name)
    if input_mode == "question":
        invalidated = {(target, model_name, question_number)}
    elif input_mode == "section":
        invalidated = {
            (target, model_name, number) for number in set(question_numbers or [])
        }
    else:
        raise ValueError(f"지원하지 않는 input_mode입니다: {input_mode}")
    kept = []
    changed = False
    for result in envelope["results"]:
        if isinstance(result, Mapping) and result.get("model_name", model_name) == model_name:
            identity = result_identity(result)
            if identity in invalidated:
                changed = True
                continue
        kept.append(result)
    if changed:
        updated = copy.deepcopy(dict(envelope))
        updated["results"] = kept
        _write_json_atomically(verified_path, updated)
    return changed


is_verified_result_completed = verified_result_is_completed
get_verified_completed_keys = verified_completed_keys


class RunStore:
    """@description 정본 실행 문서·파일 경로 저장소 래퍼"""

    def __init__(self, run: MutableMapping[str, Any], path: str | Path):
        _validate_run(run)
        self.run = run
        self.path = Path(path).expanduser().resolve()

    @classmethod
    def load(cls, path: str | Path) -> "RunStore":
        """@description 정본 파일 기준 저장소 생성"""
        return cls(load_run(path), path)

    def save(self) -> Path:
        """@description 현재 실행 저장"""
        return save_run(self.run, self.path)

    def upsert(self, result: Mapping[str, Any]) -> Dict[str, Any]:
        """@description 결과 교체 및 즉시 저장"""
        return upsert_result(self.run, result, path=self.path)


__all__ = [
    "RUN_RESULT_FILE",
    "RUN_SCHEMA_VERSION",
    "VERIFIED_RESULT_FILE",
    "RunStore",
    "canonical_results_path",
    "create_run",
    "eligible_results",
    "get_result",
    "get_verified_completed_keys",
    "initialize_model_results",
    "invalidate_verified_results",
    "is_technical_failure",
    "is_verified_result_completed",
    "load_run",
    "model_results_path",
    "model_verified_path",
    "result_identity",
    "result_is_completed",
    "result_is_eligible",
    "sanitize_model_snapshot",
    "save_run",
    "save_run_metadata",
    "upsert_result",
    "utc_now",
    "verified_completed_keys",
    "verified_result_is_completed",
]
