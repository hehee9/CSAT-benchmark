"""@description 단일 실행 결과의 채점·비공개 검증 문서 생성"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from .configuration import ConfigurationError, load_config
from .exams import ExamManifest, ModeManifest, load_exam, load_section_questions
from .grading.extractor import AnswerVerifier
from .grading.single import VerificationResult, verify_hard_single_result, verify_single_result
from .runs import canonical_results_path, load_run, model_verified_path, result_identity, result_is_completed
from .runner import RunnerError, select_sections


VERIFIED_SCHEMA_VERSION = 1


class EvaluationError(ValueError):
    """@description 채점 입력·검증기 설정·채점 계약 불일치 오류"""


def _mode_for_exam(
    exam: ExamManifest,
    mode: str | ModeManifest | None = None,
    *,
    easy: bool = False,
) -> ModeManifest:
    """@description 시험의 일반·쉬움 채점 mode 확인"""
    if easy and mode is not None:
        raise EvaluationError("--easy와 mode는 함께 지정할 수 없습니다.")
    mode_id: str | ModeManifest | None = "easy" if easy else mode
    if isinstance(mode_id, ModeManifest):
        if mode_id not in exam.modes:
            raise EvaluationError(f"시험에 속하지 않는 mode입니다: {mode_id.id}")
        return mode_id
    if mode_id is None:
        mode_id = "default" if any(item.id == "default" for item in exam.modes) else exam.modes[0].id
    for candidate in exam.modes:
        if candidate.id == mode_id:
            return candidate
    if easy:
        raise EvaluationError(f"시험 {exam.id}에는 --easy 실행을 사용할 수 없습니다.")
    available = ", ".join(candidate.id for candidate in exam.modes)
    raise EvaluationError(f"시험 {exam.id}에 mode가 없습니다: {mode_id} (사용 가능: {available})")


def resolve_run(
    exam: ExamManifest | str | Path,
    *,
    easy: bool = False,
    mode: str | ModeManifest | None = None,
    model_names: Sequence[str] | None = None,
) -> tuple[ExamManifest, ModeManifest, Dict[str, Any], Path]:
    """@description 시험·mode 기준 canonical 단일 실행 로드"""
    manifest = exam if isinstance(exam, ExamManifest) else load_exam(exam)
    selected_mode = _mode_for_exam(manifest, mode, easy=easy)
    run_path = canonical_results_path(manifest, selected_mode.id)
    if not run_path.is_file():
        raise FileNotFoundError(f"호환되는 {manifest.id}/{selected_mode.id} 실행을 찾을 수 없습니다.")

    run = load_run(run_path)
    if run["exam_id"] != manifest.id or run["mode"] != selected_mode.id:
        raise EvaluationError("실행과 시험 또는 mode가 일치하지 않습니다.")
    if run["input_mode"] != selected_mode.input_mode:
        raise EvaluationError("실행 input_mode가 시험 mode와 다릅니다.")
    if model_names is not None:
        available = {model["name"] for model in run["selected_models"]}
        unknown = set(model_names) - available
        if unknown:
            raise EvaluationError(f"실행에 없는 모델입니다: {', '.join(sorted(unknown))}")
    return manifest, selected_mode, run, run_path


def _question_numbers_for_target(run: Mapping[str, Any], target: str) -> list[int] | None:
    """@description 저장 실행 문맥에서 target별 실제 문항 번호 조회"""
    for context in run.get("input_context", []):
        if not isinstance(context, Mapping) or context.get("target") != target:
            continue
        if "question_numbers" not in context:
            return None
        values = context["question_numbers"]
        if (
            not isinstance(values, list)
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values)
            or len(values) != len(set(values))
        ):
            raise EvaluationError(f"실행 input_context의 문항 번호가 잘못되었습니다: {target}")
        return list(values)
    return None


def _question_infos(
    exam: ExamManifest,
    target: str,
    question_numbers: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    """@description 정식 문항 자료를 검증기 입력 구조로 변환"""
    section = exam.section(target)
    questions = load_section_questions(exam, section)
    if question_numbers is not None:
        requested = set(question_numbers)
        available = {question.number for question in questions}
        missing = requested - available
        if missing:
            raise EvaluationError(
                f"{target}에 실행 문맥의 문항 번호가 없습니다: {', '.join(map(str, sorted(missing)))}"
            )
        questions = [question for question in questions if question.number in requested]
    return [
        {
            "number": question.number,
            "correct_answer": question.correct_answer,
            "points": question.points,
            "question_path": question.question_path or "",
            "question_text": question.load_question_text(),
        }
        for question in questions
    ]


def _scope_sections(
    exam: ExamManifest,
    run: Mapping[str, Any],
    *,
    targets: Sequence[str] | None,
    subject: str | None,
    section: str | None,
    subjects: Sequence[str] | None,
    benchmark_all: bool,
) -> list[Any]:
    """@description 채점 선택자 기준 대상 섹션 결정"""
    has_selector = bool(targets) or subject is not None or section is not None or bool(subjects) or benchmark_all
    if not has_selector:
        stored = set(run["selected_targets"])
        return [item for item in exam.sections if item.target in stored]
    try:
        return select_sections(
            exam,
            targets=targets,
            subject=subject,
            section=section,
            subjects=subjects,
            benchmark_all=benchmark_all,
        )
    except RunnerError as error:
        raise EvaluationError(str(error)) from error


def _raw_results_by_key(run: Mapping[str, Any]) -> dict[tuple[str, str, int], Mapping[str, Any]]:
    """@description 정본 단일 생성 결과 identity 매핑 생성"""
    return {result_identity(result): result for result in run.get("results", [])}


def _verified_row(result: VerificationResult, source: Mapping[str, Any], *, complete: bool) -> dict[str, Any]:
    """@description 추출 결과와 원본 응답을 canonical verified 행으로 변환"""
    row: dict[str, Any] = {
        "target": source["target"],
        "subject": source["subject"],
        "section": source["section"],
        "model_name": result.model_name,
        "question_number": int(result.question_number),
        "extracted_answer": result.extracted_answer,
        "correct_answer": int(result.correct_answer),
        "is_correct": result.is_correct if complete else None,
        "points": int(result.points),
        "answer_status": result.answer_status if complete else "incomplete",
        "provider_stop_reason": result.provider_stop_reason,
        "needs_manual_review": bool(result.needs_manual_review),
        "complete": bool(complete),
        "raw_response": source.get("raw_response", ""),
        "provenance": "graded",
    }
    for field_name in ("input_tokens", "output_tokens", "total_tokens", "timestamp", "error_message", "error_details"):
        if field_name in source:
            row[field_name] = copy.deepcopy(source[field_name])
    return row


def _incomplete_row(source: Mapping[str, Any], info: Mapping[str, Any]) -> dict[str, Any]:
    """@description 기술적으로 완료되지 않은 원본의 미완료 verified 행 생성"""
    row: dict[str, Any] = {
        "target": source["target"],
        "subject": source["subject"],
        "section": source["section"],
        "model_name": source["model_name"],
        "question_number": int(info["number"]),
        "extracted_answer": None,
        "correct_answer": int(info["correct_answer"]),
        "is_correct": None,
        "points": int(info["points"]),
        "answer_status": "incomplete",
        "provider_stop_reason": source.get("provider_stop_reason"),
        "needs_manual_review": False,
        "complete": False,
        "raw_response": source.get("raw_response", ""),
        "provenance": "graded",
    }
    for field_name in ("input_tokens", "output_tokens", "total_tokens", "timestamp", "error_message", "error_details"):
        if field_name in source:
            row[field_name] = copy.deepcopy(source[field_name])
    return row


def _normal_verified_row(row: Mapping[str, Any], model_name: str) -> dict[str, Any]:
    """@description 기존 verified 행을 현재 canonical 필드로 정규화"""
    normalized = copy.deepcopy(dict(row))
    normalized.setdefault("model_name", model_name)
    if normalized.get("model_name") != model_name:
        raise EvaluationError(f"검증 결과 model_name이 sidecar와 다릅니다: {model_name}")
    if "complete" not in normalized:
        normalized["complete"] = normalized.get("is_correct") is not None
    normalized.setdefault("provenance", "imported_public")
    try:
        result_identity(normalized)
    except (TypeError, ValueError) as error:
        raise EvaluationError("검증 결과 identity가 잘못되었습니다.") from error
    return normalized


def _load_verified_sidecar(path: Path, *, model_name: str | None = None) -> dict[str, Any] | None:
    """@description 모델별 verified sidecar 로드"""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"검증 결과 파일을 읽을 수 없습니다: {path}") from error
    if not isinstance(payload, Mapping):
        raise EvaluationError(f"검증 결과 파일은 객체여야 합니다: {path}")
    if payload.get("schema_version", VERIFIED_SCHEMA_VERSION) != VERIFIED_SCHEMA_VERSION:
        raise EvaluationError(f"지원하지 않는 verified schema_version입니다: {payload.get('schema_version')}")
    sidecar_model = payload.get("model_name", model_name)
    if not isinstance(sidecar_model, str) or not sidecar_model:
        raise EvaluationError(f"검증 결과 model_name이 없습니다: {path}")
    if model_name is not None and sidecar_model != model_name:
        raise EvaluationError(f"검증 결과 model_name이 경로와 다릅니다: {model_name}")
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise EvaluationError(f"검증 결과 results가 목록이 아닙니다: {path}")
    normalized = [_normal_verified_row(row, sidecar_model) for row in rows if isinstance(row, Mapping)]
    if len(normalized) != len(rows):
        raise EvaluationError(f"검증 결과 항목은 객체여야 합니다: {path}")
    return {
        "schema_version": VERIFIED_SCHEMA_VERSION,
        "exam_id": payload.get("exam_id"),
        "mode": payload.get("mode"),
        "model_name": sidecar_model,
        "results": normalized,
    }


def _read_verified_for_index(index_path: Path) -> dict[str, Any]:
    """@description canonical index의 모델별 verified 결과 병합"""
    if not index_path.is_file():
        raise FileNotFoundError(f"실행 결과 파일을 찾을 수 없습니다: {index_path}")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"실행 결과 파일을 읽을 수 없습니다: {index_path}") from error
    if not isinstance(index, Mapping):
        raise EvaluationError("실행 결과 파일은 객체여야 합니다.")
    models = index.get("selected_models", [])
    names = [model.get("name") for model in models if isinstance(model, Mapping)]
    rows: list[dict[str, Any]] = []
    for model_name in names:
        sidecar = _load_verified_sidecar(model_verified_path(index_path, model_name), model_name=model_name)
        if sidecar is not None:
            if sidecar.get("exam_id") not in (None, index.get("exam_id")):
                raise EvaluationError(f"검증 결과 exam_id가 실행과 다릅니다: {model_name}")
            if sidecar.get("mode") not in (None, index.get("mode")):
                raise EvaluationError(f"검증 결과 mode가 실행과 다릅니다: {model_name}")
            rows.extend(sidecar["results"])
    wrapper = {
        "schema_version": VERIFIED_SCHEMA_VERSION,
        "exam_id": index.get("exam_id"),
        "mode": index.get("mode"),
        "selected_targets": list(index.get("selected_targets", [])),
        "selected_models": names,
        "results": rows,
    }
    contexts = index.get("input_context", [])
    expected_by_model = None
    if isinstance(contexts, list) and any(
        isinstance(context, Mapping) and "question_numbers" in context for context in contexts
    ):
        expected_by_model = {
            name: {
                (context["target"], name, number)
                for context in contexts
                if isinstance(context, Mapping) and isinstance(context.get("target"), str)
                for number in context.get("question_numbers", [])
                if isinstance(number, int) and not isinstance(number, bool)
            }
            for name in names
        }
    _attach_summary(wrapper, expected_by_model=expected_by_model)
    return wrapper


def _attach_summary(
    verified: dict[str, Any],
    *,
    expected_by_model: Mapping[str, set[tuple[str, str, int]]] | None = None,
) -> None:
    """@description verified 결과의 모델별 점수·완료 여부 계산"""
    models = list(verified.get("selected_models", []))
    score_by_model = {name: 0 for name in models}
    complete_by_model = {name: True for name in models}
    seen_by_model: dict[str, int] = {name: 0 for name in models}
    for row in verified.get("results", []):
        model_name = row.get("model_name")
        if model_name not in score_by_model:
            score_by_model[model_name] = 0
            complete_by_model[model_name] = True
            seen_by_model[model_name] = 0
        seen_by_model[model_name] += 1
        if row.get("complete") is True and row.get("is_correct") is True:
            score_by_model[model_name] += int(row.get("points", 0))
        if row.get("complete") is not True or row.get("is_correct") is None:
            complete_by_model[model_name] = False
    for model_name, count in seen_by_model.items():
        if count == 0:
            complete_by_model[model_name] = False
    if expected_by_model is not None:
        rows_by_key = {
            result_identity(row): row
            for row in verified.get("results", [])
            if isinstance(row, Mapping)
        }
        for model_name, expected in expected_by_model.items():
            complete_by_model[model_name] = bool(expected) and all(
                rows_by_key.get(key, {}).get("complete") is True
                and rows_by_key.get(key, {}).get("is_correct") is not None
                for key in expected
            )
    verified["score_by_model"] = score_by_model
    verified["complete_by_model"] = complete_by_model


def grade_run(
    run: Mapping[str, Any] | str | Path,
    exam: ExamManifest | str | Path,
    verifier: Any,
    *,
    easy: bool = False,
    mode: str | ModeManifest | None = None,
    model_names: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
    question_numbers: Sequence[int] | None = None,
    verified: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """@description 단일 생성 결과를 선택 범위만 채점"""
    manifest = exam if isinstance(exam, ExamManifest) else load_exam(exam)
    run_path: Path | None = None
    if isinstance(run, (str, Path)):
        run_path = Path(run).expanduser().resolve()
        run_data = load_run(run_path)
    else:
        run_data = copy.deepcopy(dict(run))
    selected_mode = _mode_for_exam(
        manifest, mode if easy else mode or run_data["mode"], easy=easy
    )
    if run_data.get("exam_id") != manifest.id or run_data.get("mode") != selected_mode.id:
        raise EvaluationError("실행과 시험 또는 mode가 일치하지 않습니다.")
    if run_data.get("input_mode") != selected_mode.input_mode:
        raise EvaluationError("실행 input_mode가 시험 mode와 다릅니다.")

    stored_models = [model["name"] for model in run_data["selected_models"]]
    selected_models = list(stored_models)
    if model_names is not None:
        requested = list(dict.fromkeys(model_names))
        unknown = set(requested) - set(stored_models)
        if unknown:
            raise EvaluationError(f"실행에 없는 모델입니다: {', '.join(sorted(unknown))}")
        requested_set = set(requested)
        selected_models = [name for name in stored_models if name in requested_set]

    if question_numbers is not None and any(
        isinstance(number, bool) or not isinstance(number, int) or number < 1
        for number in question_numbers
    ):
        raise EvaluationError("문항 번호는 양의 정수여야 합니다.")
    if question_numbers and selected_mode.input_mode != "question":
        raise EvaluationError("--question-numbers는 문항별 input_mode에서만 사용할 수 있습니다.")
    sections = _scope_sections(
        manifest,
        run_data,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
    )
    raw_by_key = _raw_results_by_key(run_data)

    prior: dict[str, Any] = {}
    if verified is not None:
        prior = load_verified(verified) if isinstance(verified, (str, Path)) else copy.deepcopy(dict(verified))
    elif run_path is not None:
        try:
            prior = _read_verified_for_index(run_path)
        except FileNotFoundError:
            prior = {}
    prior_rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in prior.get("results", []):
        if not isinstance(row, Mapping) or row.get("model_name") not in selected_models:
            continue
        model_name = row["model_name"]
        normalized = _normal_verified_row(row, model_name)
        prior_rows[result_identity(normalized)] = normalized

    graded_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    expected_by_model: dict[str, set[tuple[str, str, int]]] = {name: set() for name in selected_models}
    hard_cache: dict[tuple[str, str, int], dict[int, VerificationResult]] = {}
    for section_manifest in sections:
        stored_numbers = _question_numbers_for_target(run_data, section_manifest.target)
        if stored_numbers is None and selected_mode.input_mode == "question":
            stored_numbers = sorted(
                {
                    key[2]
                    for key in raw_by_key
                    if key[0] == section_manifest.target and key[1] in selected_models and key[2] > 0
                }
            )
        infos = _question_infos(manifest, section_manifest.target, stored_numbers)
        if question_numbers is not None:
            requested = set(question_numbers)
            available = {info["number"] for info in infos}
            missing = requested - available
            if missing:
                raise EvaluationError(
                    f"{section_manifest.target}에 지정한 문항 번호가 없습니다: "
                    f"{', '.join(map(str, sorted(missing)))}"
                )
            infos = [info for info in infos if info["number"] in requested]
        info_by_number = {int(info["number"]): info for info in infos}
        for model_name in selected_models:
            for number, info in info_by_number.items():
                key = (section_manifest.target, model_name, number)
                expected_by_model[model_name].add(key)
                raw_number = number if selected_mode.input_mode == "question" else 0
                source = raw_by_key.get((section_manifest.target, model_name, raw_number))
                if source is None:
                    if key in prior_rows:
                        graded_by_key[key] = copy.deepcopy(prior_rows[key])
                    continue
                if not result_is_completed(source):
                    graded_by_key[key] = _incomplete_row(source, info)
                    continue
                if selected_mode.input_mode == "question":
                    verification, _manual = verify_single_result(
                        verifier,
                        dict(source),
                        info,
                        1,
                        Path(manifest.project_root),
                    )
                    graded_by_key[key] = _verified_row(verification, source, complete=True)
                else:
                    source_key = (section_manifest.target, model_name, 0)
                    by_number = hard_cache.get(source_key)
                    if by_number is None:
                        hard_results, _manual = verify_hard_single_result(
                            verifier,
                            dict(source),
                            list(info_by_number.values()),
                            1,
                        )
                        by_number = {int(item.question_number): item for item in hard_results}
                        hard_cache[source_key] = by_number
                    graded_by_key[key] = _verified_row(by_number[number], source, complete=True)

    rows = [graded_by_key[key] for key in sorted(graded_by_key)]
    result = {
        "schema_version": VERIFIED_SCHEMA_VERSION,
        "exam_id": manifest.id,
        "mode": selected_mode.id,
        "selected_targets": [section_manifest.target for section_manifest in sections],
        "selected_models": selected_models,
        "results": rows,
    }
    _attach_summary(result, expected_by_model=expected_by_model)
    return result


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """@description JSON 원자적 저장"""
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
        ) as file:
            temporary_path = file.name
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _merge_verified_rows(
    existing: Iterable[Mapping[str, Any]],
    updates: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """@description verified 행을 identity 기준으로 교체·병합"""
    merged = {result_identity(row): copy.deepcopy(dict(row)) for row in existing}
    for row in updates:
        merged[result_identity(row)] = copy.deepcopy(dict(row))
    return [merged[key] for key in sorted(merged)]


def _verified_path_from_input(path: Path, verified: Mapping[str, Any]) -> tuple[Path, str | None]:
    """@description verified 저장 입력을 정본 색인 경로와 모델명으로 해석"""
    if path.name == "results.json":
        return path, None
    if path.name == "verified.json" and path.parent.parent.name == "models":
        return path.parents[2] / "results.json", verified.get("model_name")
    selected_models = verified.get("selected_models", [])
    one_model = verified.get("model_name") if isinstance(selected_models, list) and len(selected_models) == 1 else None
    return path, one_model


def save_verified(verified: Mapping[str, Any], path: str | Path) -> Path:
    """@description 모델별 canonical verified sidecar 저장 및 기존 행 보존"""
    if not isinstance(verified, Mapping):
        raise EvaluationError("verified는 객체여야 합니다.")
    if verified.get("schema_version", VERIFIED_SCHEMA_VERSION) != VERIFIED_SCHEMA_VERSION:
        raise EvaluationError("지원하지 않는 verified schema_version입니다.")
    rows = verified.get("results")
    if not isinstance(rows, list):
        raise EvaluationError("verified results가 목록이 아닙니다.")
    requested_path = Path(path).expanduser().resolve()
    index_path, one_model = _verified_path_from_input(requested_path, verified)
    exam_id = verified.get("exam_id")
    mode = verified.get("mode")
    if not isinstance(exam_id, str) or not exam_id.strip():
        raise EvaluationError("verified exam_id는 비어 있지 않은 문자열이어야 합니다.")
    if not isinstance(mode, str) or not mode.strip():
        raise EvaluationError("verified mode는 비어 있지 않은 문자열이어야 합니다.")
    if any(not isinstance(row, Mapping) for row in rows):
        raise EvaluationError("verified 결과 항목은 객체여야 합니다.")
    models = list(verified.get("selected_models", []))
    if any(not isinstance(model_name, str) or not model_name.strip() for model_name in models):
        raise EvaluationError("verified selected_models는 문자열 목록이어야 합니다.")
    if one_model and one_model not in models:
        models = [one_model]
    if not models:
        models = sorted({row.get("model_name") for row in rows if row.get("model_name")})
    for model_name in models:
        model_rows = [
            _normal_verified_row(row, model_name)
            for row in rows
            if row.get("model_name") == model_name
        ]
        sidecar_path = model_verified_path(index_path, model_name)
        existing = _load_verified_sidecar(sidecar_path, model_name=model_name)
        if existing is not None:
            if exam_id is not None and existing.get("exam_id") not in (None, exam_id):
                raise EvaluationError(f"기존 verified exam_id가 다릅니다: {model_name}")
            if mode is not None and existing.get("mode") not in (None, mode):
                raise EvaluationError(f"기존 verified mode가 다릅니다: {model_name}")
            existing_rows = existing["results"]
        else:
            existing_rows = []
        if not model_rows and existing is not None:
            continue
        envelope = {
            "schema_version": VERIFIED_SCHEMA_VERSION,
            "exam_id": exam_id,
            "mode": mode,
            "model_name": model_name,
            "results": _merge_verified_rows(existing_rows, model_rows),
        }
        _write_json(sidecar_path, envelope)
    return requested_path


def load_verified(path: str | Path) -> dict[str, Any]:
    """@description canonical 실행 색인 또는 모델 verified sidecar 로드"""
    source = Path(path).expanduser().resolve()
    if source.name == "results.json":
        return _read_verified_for_index(source)
    sidecar = _load_verified_sidecar(source)
    if sidecar is None:
        raise FileNotFoundError(f"검증 결과 파일을 찾을 수 없습니다: {source}")
    targets = []
    for row in sidecar["results"]:
        if row["target"] not in targets:
            targets.append(row["target"])
    wrapper = {
        **sidecar,
        "selected_targets": targets,
        "selected_models": [sidecar["model_name"]],
    }
    _attach_summary(wrapper)
    return wrapper


def build_verifier(config_path: str | Path) -> AnswerVerifier:
    """@description 지정 verifier 설정 기준 답안 추출기 생성"""
    config = load_config(config_path, model_names=[], resolve_secrets=True)
    verifier_config = config.get("verifier")
    if not isinstance(verifier_config, Mapping):
        verifier_config = {
            "api_key": os.environ.get("OPENAI_API_KEY"),
            "model_id": AnswerVerifier.MODEL_ID,
            "reasoning_effort": AnswerVerifier.REASONING_EFFORT,
        }
    api_key = verifier_config.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        raise ConfigurationError("verifier의 api_key_env로 답안 추출기 인증 정보를 지정해야 합니다.")
    return AnswerVerifier(
        api_key,
        system_prompt=verifier_config.get("system_prompt"),
        model_id=verifier_config.get("model_id"),
        reasoning_effort=verifier_config.get("reasoning_effort"),
        base_url=verifier_config.get("base_url"),
    )


__all__ = [
    "EvaluationError",
    "VERIFIED_SCHEMA_VERSION",
    "build_verifier",
    "grade_run",
    "load_verified",
    "resolve_run",
    "save_verified",
]
