"""@description 공개 설정 파일·로컬 비밀 환경 변수 결합"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Sequence

from dotenv import load_dotenv

from .metadata import validate_knowledge_cutoff, validate_plan_message


class ConfigurationError(ValueError):
    """@description 설정 구조 또는 필수 인증 정보 오류"""


def _project_root(config_path: Path) -> Path:
    """@description 설정 파일 기준 프로젝트 루트 탐색"""
    for parent in (config_path.parent, *config_path.parent.parents):
        if (parent / ".env").is_file() or (parent / ".git").exists():
            return parent
    return config_path.parent


def _credential_names(record: Dict[str, Any], env_field: str, value_field: str) -> List[str]:
    """@description 인증 정보 환경 변수명 목록 반환"""
    names = record.get(env_field)
    if isinstance(names, str):
        names = [names]
    elif isinstance(names, list):
        names = list(names)
    elif names is None and value_field in record:
        raise ConfigurationError(
            f"{record.get('name', '알 수 없는 모델')} 설정에 {env_field}가 필요합니다."
        )
    else:
        raise ConfigurationError(
            f"{record.get('name', '알 수 없는 모델')} 설정의 {env_field} 형식이 잘못되었습니다."
        )

    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ConfigurationError(
            f"{record.get('name', '알 수 없는 모델')} 설정의 {env_field} 형식이 잘못되었습니다."
        )
    return names


def _resolve_credential(
    record: Dict[str, Any],
    env_field: str,
    value_field: str,
) -> str | List[str]:
    """@description 환경 변수 인증 정보 조회 및 누락 검증"""
    names = _credential_names(record, env_field, value_field)
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        joined_names = ", ".join(missing)
        raise ConfigurationError(
            f"{record.get('name', '알 수 없는 모델')}에 필요한 환경 변수가 설정되지 않았습니다: "
            f"{joined_names}"
        )
    values = [os.environ[name] for name in names]
    return values[0] if isinstance(record.get(env_field), str) else values


def _prepare_record(record: Dict[str, Any], resolve_secrets: bool) -> Dict[str, Any]:
    """@description 모델 또는 검증기 설정 인증 정보 처리"""
    prepared = copy.deepcopy(record)
    if "api_key_env" in prepared or "api_key" in prepared:
        if resolve_secrets:
            prepared["api_key"] = _resolve_credential(prepared, "api_key_env", "api_key")
        elif "api_key_env" not in prepared:
            prepared.pop("api_key", None)
    if "vertex_key_env" in prepared or "vertex_key" in prepared:
        if resolve_secrets:
            resolved = _resolve_credential(prepared, "vertex_key_env", "vertex_key")
            if isinstance(resolved, list):
                raise ConfigurationError("vertex_key_env는 단일 환경 변수명이어야 합니다.")
            prepared["vertex_key"] = resolved
        elif "vertex_key_env" not in prepared:
            prepared.pop("vertex_key", None)
    return prepared


def load_config(
    path: str | Path,
    *,
    model_names: Sequence[str] | None = None,
    resolve_secrets: bool = True,
) -> Dict[str, Any]:
    """@description JSON 설정 로드 및 선택 모델·로컬 인증 정보 적용

    ``resolve_secrets=True``: 실행 대상 모델 설정 ``api_key``·``vertex_key`` 추가
    ``False``: 공개 설정 ``api_key_env``·``vertex_key_env`` 유지(목록·메타데이터용)
    ``model_names``: 설정 순서 기준 선택 모델명 목록
    미등록 모델명: API 호출 전 ``ConfigurationError`` 발생
    """
    config_path = Path(path).expanduser()
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ConfigurationError("설정 파일 최상위 값은 객체여야 합니다.")
    models = config.get("models")
    if not isinstance(models, list) or any(not isinstance(model, dict) for model in models):
        raise ConfigurationError("설정의 models는 객체 목록이어야 합니다.")

    root = _project_root(config_path)
    dotenv_path = root / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    if model_names is None:
        selected_models = models
    else:
        requested = [model_names] if isinstance(model_names, str) else list(model_names)
        available = [model.get("name") for model in models]
        unknown = [name for name in requested if name not in available]
        if unknown:
            raise ConfigurationError(f"등록되지 않은 모델입니다: {', '.join(unknown)}")
        requested_set = set(requested)
        selected_models = [model for model in models if model.get("name") in requested_set]

    output = copy.deepcopy(config)
    prepared_models = []
    for model in selected_models:
        prepared = _prepare_record(model, resolve_secrets)
        prepared["knowledge_cutoff"] = validate_knowledge_cutoff(
            prepared.get("knowledge_cutoff")
        )
        for field_name in ("plan_message_ko", "plan_message_en"):
            if field_name in prepared:
                prepared[field_name] = validate_plan_message(prepared[field_name], field_name)
        prepared_models.append(prepared)
    output["models"] = prepared_models
    if isinstance(output.get("verifier"), dict):
        output["verifier"] = _prepare_record(output["verifier"], resolve_secrets)
    return output
