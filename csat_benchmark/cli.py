"""@description 시험 ID 기반 실행 CLI·API Solver 진입점"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Sequence

from .configuration import load_config
from .exams import list_exams, load_exam
from .runner import RunnerError, check_exam, run_exam


def _project_root() -> Path:
    """@description 패키지 저장소 루트 반환"""
    return Path(__file__).resolve().parents[1]


def _resolve_config_path(value: str | Path | None, project_root: Path) -> Path:
    """@description 현재 작업 폴더·저장소 루트 기준 설정 파일 탐색"""
    if value is None:
        return project_root / "examples" / "config.example.json"
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    current_path = (Path.cwd() / path).resolve()
    if current_path.is_file():
        return current_path
    return (project_root / path).resolve()


def _build_parser(project_root: Path) -> argparse.ArgumentParser:
    """@description 시험 실행 인자 구성"""
    parser = argparse.ArgumentParser(
        description="시험 매니페스트 기반 수능 LLM 실행기",
        allow_abbrev=False,
    )
    parser.add_argument("--exam", help="시험 ID 또는 매니페스트 JSON 경로")
    parser.add_argument(
        "--config",
        default=str(project_root / "examples" / "config.example.json"),
        help="모델 설정 경로 (기본: examples/config.example.json)",
    )
    parser.add_argument("--models", nargs="+", help="실행할 모델 이름")
    parser.add_argument("--subject", help="한 섹션을 고를 과목")
    parser.add_argument("--section", help="한 섹션을 고를 영역")
    parser.add_argument("--targets", nargs="+", help="시험 target 목록")
    parser.add_argument("--subjects", nargs="+", help="실행할 과목 또는 탐구 영역 목록")
    parser.add_argument("--question-numbers", nargs="+", type=int, help="문항별 실행에서 고를 문제 번호")
    parser.add_argument("--benchmark-all", action="store_true", help="시험의 모든 섹션 실행")
    parser.add_argument("--output", help="결과 파일 경로 재정의")
    parser.add_argument("--output-dir", help="실행 결과 디렉터리 재정의")
    parser.add_argument("--list-models", action="store_true", help="선택 가능한 모델 목록 표시")
    parser.add_argument("--list-exams", action="store_true", help="시험 목록 표시")
    parser.add_argument("--check", action="store_true", help="API 호출 없이 시험·파일·설정 검증")
    parser.add_argument("--easy", action="store_true", help="문항별 쉬움 실행")
    parser.add_argument("--retry-failed", action="store_true", help="누락·기술 실패 결과만 재시도")
    parser.add_argument("--merge", action="store_true", help="선택 결과를 정본에 upsert")
    return parser


def _has_exam_argument(argv: Sequence[str]) -> bool:
    """@description 시험 경로 지정 인자 여부 확인"""
    return any(argument == "--exam" or argument.startswith("--exam=") for argument in argv)


def _print_exams(project_root: Path) -> None:
    """@description 시험 카탈로그 출력"""
    exams = list_exams(project_root)
    if not exams:
        print("등록된 시험이 없습니다.")
        return
    for exam in exams:
        modes = ", ".join(f"{mode.id}({mode.label}, {mode.input_mode})" for mode in exam.modes)
        print(f"{exam.id}: {exam.title} [{exam.status}] - {modes}")


def _print_models(config_path: Path, model_names: Iterable[str] | None) -> None:
    """@description 인증 정보 없이 모델 이름 출력"""
    config = load_config(config_path, model_names=model_names, resolve_secrets=False)
    for model in config["models"]:
        print(f"  - {model['name']}")


def api_main(argv: Sequence[str] | None = None) -> int:
    """@description 시험 목록·모델 목록 출력 및 선택 시험 실행"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    project_root = _project_root()
    parser = _build_parser(project_root)
    args = parser.parse_args(arguments)
    if args.list_exams:
        _print_exams(project_root)
        return 0
    config_path = _resolve_config_path(args.config, project_root)
    if args.list_models:
        try:
            _print_models(config_path, args.models)
        except (OSError, ValueError, RunnerError) as error:
            print(f"오류: {error}", file=sys.stderr)
            return 2
        return 0
    if not _has_exam_argument(arguments):
        parser.error("실행·검증에는 --exam이 필요합니다.")
    if args.subject is not None and args.section is None or args.section is not None and args.subject is None:
        parser.error("--subject와 --section은 함께 지정해야 합니다.")
    if args.output is not None and args.output_dir is not None:
        parser.error("--output과 --output-dir은 함께 사용할 수 없습니다.")

    try:
        manifest_path = Path(args.exam).expanduser()
        exam_root = manifest_path.resolve().parent if manifest_path.is_file() else project_root
        exam = load_exam(args.exam, project_root=exam_root)

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
        }
        if args.check:
            checked = check_exam(exam, **common)
            print(
                f"검증 완료: {checked['exam_id']} / {checked['mode']} - "
                f"섹션 {len(checked['targets'])}개, 모델 {len(checked['models'])}개"
            )
            return 0

        run = run_exam(
            exam,
            **common,
            output=args.output,
            output_dir=args.output_dir,
            retry_failed=args.retry_failed,
            merge=args.merge,
        )
        result_path = (
            Path(args.output).expanduser().resolve()
            if args.output
            else (
                Path(args.output_dir).expanduser().resolve() / run["mode"] / "results.json"
                if args.output_dir
                else exam.resolve_results_path(f"{run['mode']}/results.json")
            )
        )
        print(f"mode: {run['mode']}")
        print(f"결과: {result_path}")
        print(f"저장된 생성: {len(run['results'])}")
        return 0
    except (OSError, ValueError, RunnerError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 2


__all__ = ["api_main"]


if __name__ == "__main__":
    raise SystemExit(api_main())
