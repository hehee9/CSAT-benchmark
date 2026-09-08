"""@brief 모델 공개 메타데이터 검증·병합"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


_YEAR_MONTH_PATTERN = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


def validate_year_month(value: Any, field_name: str = "날짜") -> str | None:
    """@brief YYYY-MM 문자열 또는 null 검증"""
    if value is None:
        return None
    if not isinstance(value, str) or not _YEAR_MONTH_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name}은 YYYY-MM 문자열 또는 null이어야 합니다.")
    return value


def validate_knowledge_cutoff(value: Any) -> str | None:
    """@brief 모델 지식 컷오프 YYYY-MM 형식 또는 null 검증"""
    return validate_year_month(value, "knowledge_cutoff")


def validate_plan_message(value: Any, field_name: str) -> str | None:
    """@brief 모델 요금제 안내 문구 문자열 또는 null 검증"""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name}은 문자열 또는 null이어야 합니다.")
    return value


def model_snapshot_for_resume(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """@brief 재개 비교용 모델 스냅샷 표시 메타데이터 제외"""
    if not isinstance(snapshot, Mapping):
        raise TypeError("모델 스냅샷은 매핑이어야 합니다.")
    comparable = copy.deepcopy(dict(snapshot))
    comparable.pop("knowledge_cutoff", None)
    comparable.pop("plan_message_ko", None)
    comparable.pop("plan_message_en", None)
    return comparable


def _model_record(model: Any) -> Dict[str, Any]:
    """@brief 모델 자료 클래스 또는 매핑 → 독립 매핑 변환"""
    if is_dataclass(model):
        return asdict(model)
    if isinstance(model, Mapping):
        return copy.deepcopy(dict(model))
    raise TypeError("모델 설정은 매핑 또는 자료 클래스여야 합니다.")


def _iter_model_records(models: Mapping[str, Any] | Iterable[Any]) -> Iterable[Dict[str, Any]]:
    """@brief 이름 매핑 또는 모델 목록 기준 모델 설정 순회"""
    if isinstance(models, Mapping):
        for name, model in models.items():
            record = _model_record(model)
            record.setdefault("name", name)
            yield record
        return
    for model in models:
        yield _model_record(model)


def merge_model_metadata(
    existing: Mapping[str, Any],
    models: Mapping[str, Any] | Iterable[Any],
) -> Dict[str, Any]:
    """@brief 모델 설명·플래그 유지 및 설정 기반 필드 병합"""
    if not isinstance(existing, Mapping):
        raise ValueError("모델 메타데이터는 JSON 객체여야 합니다.")
    merged = copy.deepcopy(dict(existing))
    for record in _iter_model_records(models):
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("모델 설정의 name은 비어 있지 않은 문자열이어야 합니다.")
        current = merged.get(name, {})
        if not isinstance(current, Mapping):
            raise ValueError(f"모델 메타데이터 항목이 JSON 객체가 아닙니다: {name}")
        item = copy.deepcopy(dict(current))
        item["knowledgeCutoff"] = validate_knowledge_cutoff(
            record.get("knowledge_cutoff")
        )
        for language in ("ko", "en"):
            field_name = f"plan_message_{language}"
            if field_name not in record:
                continue
            value = validate_plan_message(record[field_name], field_name)
            if value is None:
                continue
            description = item.get("description", {})
            if not isinstance(description, Mapping):
                raise ValueError(f"모델 메타데이터 description이 JSON 객체가 아닙니다: {name}")
            description = copy.deepcopy(dict(description))
            if value:
                description[language] = value
            else:
                description.pop(language, None)
            if description:
                item["description"] = description
            else:
                item.pop("description", None)
        if "supports_vision" in record:
            supports_vision = record["supports_vision"]
            if not isinstance(supports_vision, bool):
                raise ValueError(f"{name}의 supports_vision은 boolean이어야 합니다.")
            if supports_vision:
                item.pop("supportsVision", None)
            else:
                item["supportsVision"] = False
        merged[name] = item
    return merged


def sync_model_metadata(
    models: Mapping[str, Any] | Iterable[Any],
    metadata_path: str | Path,
) -> bool:
    """@brief 설정 모델 메타데이터 JSON 병합 및 변경 여부 반환"""
    model_records = list(_iter_model_records(models))
    if not model_records:
        return False
    path = Path(metadata_path).expanduser().resolve()
    if path.is_file():
        original_text = path.read_text(encoding="utf-8")
        try:
            existing = json.loads(original_text)
        except json.JSONDecodeError as error:
            raise ValueError(f"모델 메타데이터 JSON 파싱 실패: {path}") from error
    else:
        original_text = ""
        existing = {}
    merged = merge_model_metadata(existing, model_records)
    updated_text = f"{json.dumps(merged, ensure_ascii=False, indent=2)}\n"
    if updated_text == original_text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated_text, encoding="utf-8")
    return True


__all__ = [
    "merge_model_metadata",
    "model_snapshot_for_resume",
    "sync_model_metadata",
    "validate_knowledge_cutoff",
    "validate_plan_message",
    "validate_year_month",
]
