"""@description 시험 매니페스트·섹션별 문항 메타데이터 로더"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .metadata import validate_year_month
from .models import Question


SCHEMA_VERSION = 1
_GROUPS = {"국어", "수학", "영어", "한국사", "탐구"}
_KINDS = {"common", "elective", "subject"}
_INPUT_MODES = {"question", "section"}


@dataclass(frozen=True)
class SectionManifest:
    """@description 시험 섹션·문항 메타데이터 경로"""

    target: str
    subject: str
    section: str
    group: str
    kind: str
    questions: str
    max_points: int


@dataclass(frozen=True)
class ModeManifest:
    """@description 시험 실행 모드·공개 결과 경로"""

    id: str
    label: str
    input_mode: str
    public_results: str | None = None
    public_token_usage: str | None = None


@dataclass(frozen=True)
class ExamManifest:
    """@description 시험 매니페스트·프로젝트 루트 정보"""

    schema_version: int
    id: str
    title: str
    data_dir: str
    results_dir: str
    sections: List[SectionManifest]
    modes: List[ModeManifest]
    publish: bool = True
    status: str = "ready"
    short_name: str = ""
    exam_month: str | None = None
    project_root: Path = field(default_factory=Path.cwd, repr=False, compare=False)
    manifest_path: Path | None = field(default=None, repr=False, compare=False)

    @property
    def data_root(self) -> Path:
        """@description 문항 데이터 루트 경로 반환"""
        return _resolve_relative_path(self.project_root, self.data_dir, "data_dir")

    @property
    def results_root(self) -> Path:
        """@description 실행 결과 저장 루트 경로 반환"""
        return _resolve_relative_path(self.project_root, self.results_dir, "results_dir")

    def resolve_project_path(self, relative_path: str) -> Path:
        """@description 프로젝트 루트 기준 공개 파일 경로 반환"""
        return _resolve_relative_path(self.project_root, relative_path, "공개 결과 경로")

    def resolve_data_path(self, relative_path: str) -> Path:
        """@description 시험 데이터 루트 기준 절대 경로 반환"""
        return _resolve_relative_path(self.data_root, relative_path, "문항 경로")

    def resolve_results_path(self, relative_path: str) -> Path:
        """@description 시험 결과 루트 기준 절대 경로 반환"""
        return _resolve_relative_path(self.results_root, relative_path, "결과 경로")

    def section(self, target: str) -> SectionManifest:
        """@description CLI target 기준 섹션 조회"""
        for section in self.sections:
            if section.target == target:
                return section
        available = ", ".join(section.target for section in self.sections)
        raise KeyError(f"시험 {self.id}에 섹션이 없습니다: {target} (사용 가능: {available})")


def _default_project_root() -> Path:
    """@description 패키지 상위 프로젝트 루트 반환"""
    return Path(__file__).resolve().parents[1]


def _resolve_relative_path(base: Path, relative_path: str, label: str) -> Path:
    """@description 프로젝트 내부 상대 경로 검증 및 절대 경로 변환"""
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError(f"{label}은 비어 있지 않은 문자열이어야 합니다.")
    raw_path = Path(relative_path)
    if raw_path.is_absolute():
        raise ValueError(f"{label}은 프로젝트 내부 상대 경로여야 합니다: {relative_path}")
    base_path = base.resolve()
    resolved = (base_path / raw_path).resolve()
    try:
        resolved.relative_to(base_path)
    except ValueError as error:
        raise ValueError(f"{label}이 허용된 경로를 벗어납니다: {relative_path}") from error
    return resolved


def _require_string(record: Dict[str, Any], key: str, context: str) -> str:
    """@description 매니페스트 필수 문자열 필드 반환"""
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key}는 비어 있지 않은 문자열이어야 합니다.")
    return value


def _parse_section(record: Any, index: int) -> SectionManifest:
    """@description 매니페스트 섹션 객체 검증"""
    context = f"sections[{index}]"
    if not isinstance(record, dict):
        raise ValueError(f"{context}는 객체여야 합니다.")
    target = _require_string(record, "target", context)
    subject = _require_string(record, "subject", context)
    section = _require_string(record, "section", context)
    group = _require_string(record, "group", context)
    kind = _require_string(record, "kind", context)
    questions = _require_string(record, "questions", context)
    max_points = record.get("max_points")
    if isinstance(max_points, bool) or not isinstance(max_points, int) or max_points < 1:
        raise ValueError(f"{context}.max_points는 양의 정수여야 합니다.")
    if group not in _GROUPS:
        raise ValueError(f"{context}.group이 지원되지 않습니다: {group}")
    if kind not in _KINDS:
        raise ValueError(f"{context}.kind가 지원되지 않습니다: {kind}")
    return SectionManifest(target, subject, section, group, kind, questions, max_points)


def _parse_mode(record: Any, index: int) -> ModeManifest:
    """@description 매니페스트 실행 모드 객체 검증"""
    context = f"modes[{index}]"
    if not isinstance(record, dict):
        raise ValueError(f"{context}는 객체여야 합니다.")
    mode_id = _require_string(record, "id", context)
    label = _require_string(record, "label", context)
    input_mode = _require_string(record, "input_mode", context)
    if input_mode not in _INPUT_MODES:
        raise ValueError(f"{context}.input_mode가 지원되지 않습니다: {input_mode}")
    public_results = record.get("public_results")
    public_token_usage = record.get("public_token_usage")
    for key, value in (("public_results", public_results), ("public_token_usage", public_token_usage)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{context}.{key}는 문자열 또는 null이어야 합니다.")
    return ModeManifest(mode_id, label, input_mode, public_results, public_token_usage)


def validate_exam(exam: ExamManifest) -> None:
    """@description 시험 매니페스트 구조·내부 상대 경로 검증

    성공 시 ``None`` 반환, 잘못된 매니페스트 ``ValueError`` 보고
    데이터 파일 존재 여부 섹션 로드 시 검사
    """
    if exam.schema_version != SCHEMA_VERSION:
        raise ValueError(f"지원하지 않는 schema_version입니다: {exam.schema_version}")
    if not exam.id or not exam.title:
        raise ValueError("시험 id와 title은 비어 있을 수 없습니다.")
    if not isinstance(exam.short_name, str) or not exam.short_name.strip():
        raise ValueError("시험 short_name은 비어 있지 않은 문자열이어야 합니다.")
    validate_year_month(exam.exam_month, "시험 exam_month")
    if not exam.sections:
        raise ValueError("시험에는 하나 이상의 sections가 필요합니다.")
    if not exam.modes:
        raise ValueError("시험에는 하나 이상의 modes가 필요합니다.")
    if not isinstance(exam.publish, bool):
        raise ValueError("시험 publish는 boolean이어야 합니다.")
    if not isinstance(exam.status, str) or not exam.status.strip():
        raise ValueError("시험 status는 비어 있지 않은 문자열이어야 합니다.")

    _resolve_relative_path(exam.project_root, exam.data_dir, "data_dir")
    _resolve_relative_path(exam.project_root, exam.results_dir, "results_dir")
    targets = set()
    for section in exam.sections:
        if section.target in targets:
            raise ValueError(f"섹션 target이 중복됩니다: {section.target}")
        targets.add(section.target)
        if section.group not in _GROUPS or section.kind not in _KINDS:
            raise ValueError(f"지원되지 않는 섹션 분류입니다: {section.target}")
        _resolve_relative_path(exam.data_root, section.questions, "questions")
    mode_ids = set()
    for mode in exam.modes:
        if mode.id in mode_ids:
            raise ValueError(f"실행 mode id가 중복됩니다: {mode.id}")
        mode_ids.add(mode.id)
        if mode.input_mode not in _INPUT_MODES:
            raise ValueError(f"지원되지 않는 실행 mode입니다: {mode.id}")
        if mode.public_results is not None:
            _resolve_relative_path(exam.project_root, mode.public_results, "public_results")
        if mode.public_token_usage is not None:
            _resolve_relative_path(exam.project_root, mode.public_token_usage, "public_token_usage")


def _parse_exam(payload: Any, project_root: Path, manifest_path: Path) -> ExamManifest:
    """@description JSON 객체 → ExamManifest 변환"""
    if not isinstance(payload, dict):
        raise ValueError("시험 매니페스트 최상위 값은 객체여야 합니다.")
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"지원하지 않는 schema_version입니다: {schema_version}")
    sections_data = payload.get("sections")
    modes_data = payload.get("modes")
    if not isinstance(sections_data, list) or not isinstance(modes_data, list):
        raise ValueError("시험 sections와 modes는 목록이어야 합니다.")
    title = _require_string(payload, "title", "exam")
    exam = ExamManifest(
        schema_version=schema_version,
        id=_require_string(payload, "id", "exam"),
        title=title,
        data_dir=_require_string(payload, "data_dir", "exam"),
        results_dir=_require_string(payload, "results_dir", "exam"),
        sections=[_parse_section(record, index) for index, record in enumerate(sections_data)],
        modes=[_parse_mode(record, index) for index, record in enumerate(modes_data)],
        publish=payload.get("publish", True),
        status=payload.get("status", "ready"),
        short_name=payload.get("short_name", title),
        exam_month=payload.get("exam_month"),
        project_root=project_root,
        manifest_path=manifest_path,
    )
    validate_exam(exam)
    return exam


def load_exam(identifier_or_path: str | Path, project_root: str | Path | None = None) -> ExamManifest:
    """@description 시험 ID 또는 매니페스트 경로 로드

    ID ``csat-2026`` 해석 경로 ``<project_root>/benchmarks/csat-2026.json``
    반환값 ``ExamManifest``, 섹션 조회 ``exam.section(target)``
    """
    root = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else _default_project_root()
    )
    raw_identifier = Path(identifier_or_path).expanduser()
    if raw_identifier.is_absolute():
        manifest_path = raw_identifier.resolve()
    elif raw_identifier.suffix == ".json" or len(raw_identifier.parts) > 1:
        manifest_path = (raw_identifier if raw_identifier.exists() else root / raw_identifier).resolve()
    else:
        manifest_path = (root / "benchmarks" / f"{raw_identifier.name}.json").resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"시험 매니페스트를 찾을 수 없습니다: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        payload = json.load(manifest_file)
    return _parse_exam(payload, root, manifest_path)


def list_exams(project_root: str | Path | None = None) -> List[ExamManifest]:
    """@description benchmarks 디렉터리 전체 시험 ID 순서 반환

    ``publish=false`` 예시 포함, 공개 카탈로그 필터링 기준 ``publish`` 값 제공
    """
    root = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else _default_project_root()
    )
    benchmark_dir = root / "benchmarks"
    if not benchmark_dir.is_dir():
        return []
    return [load_exam(path, project_root=root) for path in sorted(benchmark_dir.glob("*.json"))]


def _section_from_argument(exam: ExamManifest, section: str | SectionManifest) -> SectionManifest:
    """@description 섹션 target 또는 SectionManifest 확인"""
    if isinstance(section, SectionManifest):
        if section not in exam.sections:
            raise KeyError(f"시험 {exam.id}에 속하지 않는 섹션입니다: {section.target}")
        return section
    if isinstance(section, str):
        return exam.section(section)
    raise TypeError("section은 target 문자열 또는 SectionManifest여야 합니다.")


def _read_section_questions(exam: ExamManifest, section: SectionManifest) -> Dict[str, Any]:
    """@description 섹션 questions.json 로드 및 기본 구조 확인"""
    questions_path = exam.resolve_data_path(section.questions)
    if not questions_path.is_file():
        raise FileNotFoundError(f"섹션 문항 메타데이터를 찾을 수 없습니다: {questions_path}")
    with questions_path.open("r", encoding="utf-8") as questions_file:
        payload = json.load(questions_file)
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise ValueError(f"섹션 문항 메타데이터 형식이 잘못되었습니다: {questions_path}")
    for key, expected in (("subject", section.subject), ("section", section.section)):
        if payload.get(key) != expected:
            raise ValueError(
                f"{questions_path}의 {key}가 매니페스트와 다릅니다: "
                f"{payload.get(key)!r} != {expected!r}"
            )
    return payload


def _path_list(record: Dict[str, Any], key: str, exam: ExamManifest) -> List[str]:
    """@description 문항 미디어 상대 경로 목록 → 시험 데이터 절대 경로 변환"""
    paths = record.get(key, [])
    if paths is None:
        return []
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError(f"문항 {record.get('number')}의 {key} 형식이 잘못되었습니다.")
    return [str(exam.resolve_data_path(path)) for path in paths]


def _question_from_record(record: Any, exam: ExamManifest) -> Question:
    """@description JSON 문항 객체 → 공용 Question 변환"""
    if not isinstance(record, dict):
        raise ValueError("문항 항목은 객체여야 합니다.")
    required = ("number", "correct_answer", "points")
    if any(key not in record for key in required):
        raise ValueError(f"문항에 필수 필드가 없습니다: {required}")
    values = {key: record[key] for key in required}
    if (
        isinstance(values["number"], bool)
        or not isinstance(values["number"], int)
        or isinstance(values["points"], bool)
        or not isinstance(values["points"], int)
    ):
        raise ValueError(f"문항 번호·배점은 정수여야 합니다: {values}")
    if values["points"] < 1:
        raise ValueError(f"문항 배점은 양수여야 합니다: {values['points']}")
    question_path = record.get("question_path")
    if question_path is not None:
        if not isinstance(question_path, str) or not question_path.strip():
            raise ValueError(f"문항 {values['number']}의 question_path 형식이 잘못되었습니다.")
        question_path = str(exam.resolve_data_path(question_path))
    question_text = record.get("question_text")
    if question_text is not None and not isinstance(question_text, str):
        raise ValueError(f"문항 {values['number']}의 question_text 형식이 잘못되었습니다.")
    elective = record.get("elective")
    if elective is not None and not isinstance(elective, str):
        raise ValueError(f"문항 {values['number']}의 elective 형식이 잘못되었습니다.")
    return Question(
        number=values["number"],
        correct_answer=values["correct_answer"],
        points=values["points"],
        question_path=question_path,
        image_paths=_path_list(record, "image_paths", exam),
        pdf_paths=_path_list(record, "pdf_paths", exam),
        audio_paths=_path_list(record, "audio_paths", exam),
        video_paths=_path_list(record, "video_paths", exam),
        question_text=question_text,
        elective=elective,
    )


def validate_section_questions(
    exam: ExamManifest,
    section: str | SectionManifest,
) -> None:
    """@description 섹션 문항 메타데이터 구조·경로 검증

    성공 시 ``None`` 반환
    문항 본문·미디어 파일 미준비 시험: ``load_section_questions`` 호출 시
    파일 존재 여부 별도 확인
    """
    _load_section_question_list(exam, _section_from_argument(exam, section))


def _load_section_question_list(exam: ExamManifest, section: SectionManifest) -> List[Question]:
    """@description 섹션 문항 목록 변환 및 배점 검증"""
    payload = _read_section_questions(exam, section)
    questions = [_question_from_record(record, exam) for record in payload["questions"]]
    if not questions:
        raise ValueError(f"섹션에 문항이 없습니다: {section.target}")
    numbers = [question.number for question in questions]
    if len(numbers) != len(set(numbers)):
        raise ValueError(f"섹션 문항 번호가 중복됩니다: {section.target}")
    total_points = sum(question.points for question in questions)
    if total_points != section.max_points:
        raise ValueError(
            f"{section.target} 배점 합계가 매니페스트와 다릅니다: "
            f"{total_points} != {section.max_points}"
        )
    return questions


def load_section_questions(
    exam: ExamManifest,
    section: str | SectionManifest,
) -> List[Question]:
    """@description 섹션 문항 메타데이터 → ``Question`` 목록 로드

    ``section``: 매니페스트 CLI target 문자열(예: ``국어/공통``) 또는
    ``SectionManifest``
    문항·미디어 경로: 시험 데이터 루트 기준 절대 경로
    성공 시 ``list[Question]`` 반환
    """
    return _load_section_question_list(exam, _section_from_argument(exam, section))
