"""@description 시험 매니페스트 기준 단일 생성·정본 저장 실행기"""

from __future__ import annotations

import copy
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

from .configuration import load_config
from .exams import ExamManifest, ModeManifest, SectionManifest, load_exam, load_section_questions
from .models import APIResponse, ModelConfig, Question
from .providers import build_hard_section_text_blocks, create_provider_client
from .providers.requests import validate_question_media
from .runs import (
    RUN_RESULT_FILE,
    RunStore,
    canonical_results_path,
    create_run,
    get_result,
    initialize_model_results,
    invalidate_verified_results,
    result_is_completed,
    sanitize_model_snapshot,
    save_run_metadata,
    verified_result_is_completed,
)


class RunnerError(RuntimeError):
    """@description 실행 선택·정본 저장 조건 오류"""


class ImmediateJob:
    """@description 공급자 전송용 단일 생성 작업"""

    def __init__(
        self,
        *,
        target: str,
        subject: str,
        section: str,
        model_name: str,
        question_number: int,
        question: Question,
    ) -> None:
        self.target = target
        self.subject = subject
        self.section = section
        self.model_name = model_name
        self.question_number = question_number
        self.question = question

    @property
    def identity(self) -> tuple[str, str, int]:
        """@description 저장 결과용 작업 식별키 반환"""
        return self.target, self.model_name, self.question_number


def _resolve_manifest(exam: ExamManifest | str | Path) -> ExamManifest:
    """@description 시험 ID·경로·매니페스트 입력 통일"""
    if isinstance(exam, ExamManifest):
        return exam
    return load_exam(exam)


def _resolve_mode(
    exam: ExamManifest,
    mode: ModeManifest | str | None,
    *,
    easy: bool = False,
) -> ModeManifest:
    """@description 일반·쉬움 실행 mode 확인"""
    if easy and mode is not None:
        raise RunnerError("--easy와 명시적 mode는 함께 사용할 수 없습니다.")
    mode_id = "easy" if easy else mode
    if isinstance(mode_id, ModeManifest):
        if mode_id not in exam.modes:
            raise RunnerError(f"시험 {exam.id}에 속하지 않는 mode입니다: {mode_id.id}")
        return mode_id
    if mode_id is None:
        mode_id = "default" if any(item.id == "default" for item in exam.modes) else exam.modes[0].id
    for item in exam.modes:
        if item.id == mode_id:
            return item
    if easy:
        raise RunnerError(f"시험 {exam.id}에는 --easy 실행을 사용할 수 없습니다.")
    raise RunnerError(
        f"시험 {exam.id}에 mode가 없습니다: {mode_id} "
        f"(사용 가능: {', '.join(item.id for item in exam.modes)})"
    )


def select_sections(
    exam: ExamManifest,
    *,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
) -> List[SectionManifest]:
    """@description CLI 선택 조건 기준 시험 매니페스트 섹션 목록 변환"""
    selectors = sum(
        bool(value)
        for value in (
            targets,
            subject is not None or section is not None,
            subjects,
            benchmark_all,
        )
    )
    if selectors > 1:
        raise RunnerError("target·subject/section·subjects·benchmark-all 선택은 하나만 사용할 수 있습니다.")
    if (subject is None) != (section is None):
        raise RunnerError("--subject와 --section은 함께 지정해야 합니다.")

    if targets:
        selected = []
        seen: set[str] = set()
        for target in targets:
            if not isinstance(target, str) or not target.strip():
                raise RunnerError("target은 비어 있지 않은 문자열이어야 합니다.")
            target = target.strip()
            if target in seen:
                continue
            selected.append(exam.section(target))
            seen.add(target)
        return selected

    if subject is not None and section is not None:
        exact_target = f"{subject}/{section}"
        try:
            return [exam.section(exact_target)]
        except KeyError:
            for item in exam.sections:
                if item.subject == subject and item.section == section:
                    return [item]
            raise RunnerError(f"시험 {exam.id}에 섹션이 없습니다: {exact_target}")

    if subjects:
        requested = {item.strip() for item in subjects if item.strip()}
        if not requested:
            raise RunnerError("--subjects에는 하나 이상의 과목을 지정해야 합니다.")
        selected = [
            item
            for item in exam.sections
            if item.group in requested
            or item.subject in requested
            or item.target.split("/", 1)[0] in requested
        ]
        if not selected:
            raise RunnerError(f"선택한 과목에 해당하는 시험 섹션이 없습니다: {', '.join(requested)}")
        return selected

    return list(exam.sections)


def _unique_paths(questions: Iterable[Question], field_name: str) -> List[str]:
    """@description 정규화 파일 경로 기준 매체 중복 제거 및 최초 경로 보존"""
    paths: List[str] = []
    seen: set[str] = set()
    for question in questions:
        for path in getattr(question, field_name):
            normalized = os.path.normcase(os.path.normpath(str(Path(path).expanduser().resolve())))
            if normalized not in seen:
                paths.append(path)
                seen.add(normalized)
    return paths


def _validate_question_files(questions: Sequence[Question]) -> None:
    """@description 요청 전 본문·선언 미디어 파일 존재 여부 확인"""
    media_fields = ("image_paths", "pdf_paths", "audio_paths", "video_paths")
    for question in questions:
        if question.question_text is None and question.question_path:
            if not Path(question.question_path).is_file():
                raise FileNotFoundError(f"문항 본문 파일을 찾을 수 없습니다: {question.question_path}")
        elif (
            question.question_text is None
            and not question.question_path
            and not any(getattr(question, field_name) for field_name in media_fields)
        ):
            raise ValueError(f"문항 {question.number}에 본문 경로 또는 본문이 없습니다.")
        for field_name in media_fields:
            for path in getattr(question, field_name):
                if not Path(path).is_file():
                    raise FileNotFoundError(f"문항 {question.number}의 미디어 파일을 찾을 수 없습니다: {path}")
        question.load_question_text()


def _question_context(question: Question) -> Dict[str, Any]:
    """@description 준비 입력 조건의 저장용 매핑 변환"""
    return {
        "number": question.number,
        "question_text": question.load_question_text(),
        "image_paths": list(question.image_paths),
        "pdf_paths": list(question.pdf_paths),
        "audio_paths": list(question.audio_paths),
        "video_paths": list(question.video_paths),
    }


def _validate_prepared_media(
    prepared: Mapping[str, Sequence[tuple[Question, int]]],
    model_configs: Mapping[str, ModelConfig],
) -> None:
    """@description 준비 문항·선택 모델 매체 지원 범위 검증"""
    for questions in prepared.values():
        for question, _ in questions:
            for model_config in model_configs.values():
                validate_question_media(question, model_config)


def _prepare_sections(
    exam: ExamManifest,
    sections: Sequence[SectionManifest],
    mode: ModeManifest,
    question_numbers: Sequence[int] | None,
) -> tuple[List[Dict[str, Any]], Dict[str, List[tuple[Question, int]]]]:
    """@description 선택 섹션 입력 검증 및 단일 생성 문항 준비"""
    if question_numbers and mode.input_mode != "question":
        raise RunnerError("--question-numbers는 문항별 input_mode에서만 사용할 수 있습니다.")
    requested_numbers = set(question_numbers or [])
    if any(isinstance(number, bool) or not isinstance(number, int) or number < 1 for number in requested_numbers):
        raise RunnerError("문항 번호는 양의 정수여야 합니다.")

    contexts: List[Dict[str, Any]] = []
    prepared: Dict[str, List[tuple[Question, int]]] = {}
    for section in sections:
        questions = load_section_questions(exam, section)
        _validate_question_files(questions)
        if requested_numbers:
            available = {question.number for question in questions}
            missing = requested_numbers - available
            if missing:
                raise RunnerError(
                    f"{section.target}에 지정한 문항 번호가 없습니다: {', '.join(map(str, sorted(missing)))}"
                )
            questions = [question for question in questions if question.number in requested_numbers]

        context: Dict[str, Any] = {
            "target": section.target,
            "subject": section.subject,
            "section": section.section,
            "input_mode": mode.input_mode,
            "question_numbers": [question.number for question in questions],
            "questions": [_question_context(question) for question in questions],
        }
        if mode.input_mode == "section":
            text_blocks = build_hard_section_text_blocks(questions)
            bundled_question = Question(
                number=0,
                correct_answer=0,
                points=sum(question.points for question in questions),
                image_paths=_unique_paths(questions, "image_paths"),
                pdf_paths=_unique_paths(questions, "pdf_paths"),
                audio_paths=_unique_paths(questions, "audio_paths"),
                video_paths=_unique_paths(questions, "video_paths"),
                question_text="\n\n---\n\n".join(text_blocks),
            )
            context["prepared_question"] = _question_context(bundled_question)
            prepared[section.target] = [(bundled_question, 0)]
        else:
            prepared[section.target] = [(question, question.number) for question in questions]
        contexts.append(context)
    return contexts, prepared


def _model_config_from_record(record: Mapping[str, Any], *, allow_missing_key: bool) -> ModelConfig:
    """@description 설정 매핑 기준 공용 ModelConfig 변환"""
    allowed = {field.name for field in fields(ModelConfig)}
    values = {key: value for key, value in record.items() if key in allowed}
    if allow_missing_key and "api_key" not in values:
        values["api_key"] = ""
    return ModelConfig(**values)


def _load_model_configs(
    config_path: str | Path,
    model_names: Sequence[str] | None,
    *,
    resolve_secrets: bool,
) -> tuple[Dict[str, ModelConfig], Dict[str, Dict[str, Any]], str]:
    """@description 선택 모델 설정·저장용 설정 매핑 로드"""
    config = load_config(config_path, model_names=model_names, resolve_secrets=resolve_secrets)
    records = config.get("models", [])
    model_configs: Dict[str, ModelConfig] = {}
    snapshots: Dict[str, Dict[str, Any]] = {}
    for record in records:
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RunnerError("모델 설정의 name은 비어 있지 않은 문자열이어야 합니다.")
        if name in model_configs:
            raise RunnerError(f"모델 설정 name이 중복됩니다: {name}")
        model_configs[name] = _model_config_from_record(
            record,
            allow_missing_key=not resolve_secrets,
        )
        snapshots[name] = sanitize_model_snapshot(record)
    if not model_configs:
        raise RunnerError("실행할 모델이 없습니다.")
    system_prompt = config.get("system_prompt", "")
    if not isinstance(system_prompt, str):
        raise RunnerError("설정 system_prompt는 문자열이어야 합니다.")
    return model_configs, snapshots, system_prompt


def check_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    mode: ModeManifest | str | None = None,
    easy: bool = False,
    model_names: Sequence[str] | None = None,
    targets: Sequence[str] | None = None,
    subject: str | None = None,
    section: str | None = None,
    subjects: Sequence[str] | None = None,
    benchmark_all: bool = False,
    question_numbers: Sequence[int] | None = None,
) -> Dict[str, Any]:
    """@description API 호출 없이 시험 파일·선택 모델 설정 검증"""
    manifest = _resolve_manifest(exam)
    selected_mode = _resolve_mode(manifest, mode, easy=easy)
    selected_sections = select_sections(
        manifest,
        targets=targets,
        subject=subject,
        section=section,
        subjects=subjects,
        benchmark_all=benchmark_all,
    )
    contexts, prepared = _prepare_sections(manifest, selected_sections, selected_mode, question_numbers)
    model_configs, snapshots, _ = _load_model_configs(
        config_path,
        model_names,
        resolve_secrets=False,
    )
    _validate_prepared_media(prepared, model_configs)
    return {
        "exam_id": manifest.id,
        "mode": selected_mode.id,
        "input_mode": selected_mode.input_mode,
        "targets": [item.target for item in selected_sections],
        "models": list(model_configs),
        "input_context": contexts,
        "model_snapshots": snapshots,
    }


def _run_path(
    exam: ExamManifest,
    mode: ModeManifest,
    *,
    output: str | Path | None,
    output_dir: str | Path | None,
) -> Path:
    """@description 정본 결과 파일 경로 계산"""
    if output is not None:
        return Path(output).expanduser().resolve()
    if output_dir is not None:
        return Path(output_dir).expanduser().resolve() / mode.id / RUN_RESULT_FILE
    return canonical_results_path(exam, mode.id)


def _merge_contexts(
    stored: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    """@description 저장 입력 문맥에 현재 선택 문항을 target별 병합"""
    merged = [copy.deepcopy(dict(context)) for context in stored]
    by_target = {
        context.get("target"): context
        for context in merged
        if isinstance(context, Mapping) and context.get("target")
    }
    for current_context in current:
        target = current_context["target"]
        existing = by_target.get(target)
        if existing is None:
            copied = copy.deepcopy(dict(current_context))
            merged.append(copied)
            by_target[target] = copied
            continue
        question_numbers = list(
            dict.fromkeys(
                [
                    *existing.get("question_numbers", []),
                    *current_context.get("question_numbers", []),
                ]
            )
        )
        old_questions = {item["number"]: item for item in existing.get("questions", [])}
        for question in current_context.get("questions", []):
            old_questions.setdefault(question["number"], copy.deepcopy(question))
        existing["question_numbers"] = question_numbers
        existing["questions"] = list(old_questions.values())
        if "prepared_question" in current_context:
            existing["prepared_question"] = copy.deepcopy(current_context["prepared_question"])
    return merged


def _merge_stored_run(
    stored: Mapping[str, Any],
    current: Mapping[str, Any],
) -> Dict[str, Any]:
    """@description 기존 정본과 현재 선택 범위·모델 설정 병합"""
    merged = copy.deepcopy(dict(stored))
    merged["selected_targets"] = list(stored["selected_targets"])
    for target in current["selected_targets"]:
        if target not in merged["selected_targets"]:
            merged["selected_targets"].append(target)
    model_by_name = {model["name"]: model for model in stored["selected_models"]}
    for model in current["selected_models"]:
        model_by_name[model["name"]] = copy.deepcopy(model)
    merged["selected_models"] = list(model_by_name.values())
    merged["input_context"] = _merge_contexts(stored.get("input_context", []), current["input_context"])
    merged["system_prompt"] = current.get("system_prompt", stored.get("system_prompt", ""))
    merged["results"] = copy.deepcopy(stored.get("results", []))
    return merged


def _response_record(response: APIResponse, job: ImmediateJob) -> Dict[str, Any]:
    """@description 공용 APIResponse를 정본 결과 레코드로 변환"""
    if not isinstance(response, APIResponse):
        raise TypeError("공급자 send_request는 APIResponse를 반환해야 합니다.")
    record = asdict(response)
    record.update(
        {
            "target": job.target,
            "subject": job.subject,
            "section": job.section,
            "model_name": job.model_name,
            "question_number": job.question_number,
        }
    )
    return record


def run_exam(
    exam: ExamManifest | str | Path,
    *,
    config_path: str | Path,
    mode: ModeManifest | str | None = None,
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
    merge: bool = False,
    client_factory: Callable[..., Any] | None = None,
) -> Dict[str, Any]:
    """@description 선택 시험 섹션·모델 단일 생성 및 정본 즉시 저장"""
    manifest = _resolve_manifest(exam)
    selected_mode = _resolve_mode(manifest, mode, easy=easy)
    if output is not None and output_dir is not None:
        raise RunnerError("output과 output_dir은 함께 사용할 수 없습니다.")
    run_path = _run_path(manifest, selected_mode, output=output, output_dir=output_dir)
    existing_path = run_path.is_file()
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
    _validate_prepared_media(prepared, model_configs)

    current_run = create_run(
        exam_id=manifest.id,
        mode=selected_mode.id,
        input_mode=selected_mode.input_mode,
        selected_targets=[item.target for item in selected_sections],
        selected_models=[snapshots[name] for name in model_configs],
        input_context=contexts,
        system_prompt=system_prompt,
    )
    stored_model_names: set[str] = set()
    if existing_path:
        stored_run = RunStore.load(run_path).run
        if stored_run["exam_id"] != manifest.id or stored_run["mode"] != selected_mode.id:
            raise RunnerError("기존 정본 시험·mode가 현재 선택과 다릅니다.")
        stored_model_names = {model["name"] for model in stored_run["selected_models"]}
        run = _merge_stored_run(stored_run, current_run)
    else:
        run = current_run
    # merge는 정본 구조에서 항상 선택 key upsert가 되므로 별도 latest 조회가 필요 없다.
    _ = merge
    store = RunStore(run, run_path)
    if not existing_path:
        store.save()

    context_by_target = {context["target"]: context for context in contexts}
    selected_model_names = list(model_configs)
    jobs: List[ImmediateJob] = []
    for section_manifest in selected_sections:
        actual_numbers = context_by_target[section_manifest.target]["question_numbers"]
        for question, question_number in prepared[section_manifest.target]:
            for model_name in selected_model_names:
                previous = get_result(run, (section_manifest.target, model_name, question_number))
                if retry_failed:
                    if previous is not None and result_is_completed(previous):
                        continue
                    if verified_result_is_completed(
                        run_path,
                        model_name,
                        section_manifest.target,
                        question_number,
                        input_mode=selected_mode.input_mode,
                        question_numbers=actual_numbers,
                    ):
                        continue
                jobs.append(
                    ImmediateJob(
                        target=section_manifest.target,
                        subject=section_manifest.subject,
                        section=section_manifest.section,
                        model_name=model_name,
                        question_number=question_number,
                        question=question,
                    )
                )

    if existing_path:
        new_raw_model_names = sorted({job.model_name for job in jobs} - stored_model_names)
        if new_raw_model_names:
            initialize_model_results(run, run_path, new_raw_model_names)
            save_run_metadata(run, run_path)

    for job in jobs:
        invalidate_verified_results(
            run_path,
            job.model_name,
            job.target,
            job.question_number,
            input_mode=selected_mode.input_mode,
            question_numbers=context_by_target[job.target]["question_numbers"],
        )

    factory = create_provider_client if client_factory is None else client_factory
    clients: Dict[str, Any] = {}
    active_model_names = {job.model_name for job in jobs}
    for model_name, model_config in model_configs.items():
        if model_name in active_model_names:
            clients[model_name] = factory(model_config, system_prompt=system_prompt)

    limits = {name: model_configs[name].concurrent_request_limit for name in selected_model_names}
    max_workers = min(max(1, sum(limits.values())), max(1, len(jobs)))
    semaphores = {name: threading.Semaphore(limits[name]) for name in selected_model_names}

    def invoke(job: ImmediateJob) -> APIResponse:
        """@description 작업별 모델 동시성 슬롯 실행"""
        with semaphores[job.model_name]:
            return clients[job.model_name].send_request(job.question)

    if jobs:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(invoke, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                store.upsert(_response_record(future.result(), job))
    elif existing_path:
        save_run_metadata(store.run, run_path)
    return store.run


__all__ = ["ImmediateJob", "RunnerError", "check_exam", "run_exam", "select_sections"]
