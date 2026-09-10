"""@description 시험 단일 실행 답안 채점 진입점"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from csat_benchmark.evaluation import EvaluationError, build_verifier, grade_run, resolve_run, save_verified
from csat_benchmark.exams import load_exam


def _build_parser() -> argparse.ArgumentParser:
    """@description 단일 실행 답안 채점 인자 구성"""
    parser = argparse.ArgumentParser(
        description="시험 단일 실행 답안 검증",
        allow_abbrev=False,
    )
    parser.add_argument("--exam", required=True, help="시험 ID 또는 매니페스트 경로")
    parser.add_argument("--easy", action="store_true", help="문항별 쉬움 실행 선택")
    parser.add_argument("--config", default="config.json", help="verifier 설정 경로")
    parser.add_argument("--models", nargs="+", help="검증할 모델명")
    parser.add_argument("--targets", nargs="+", help="시험 target 목록")
    parser.add_argument("--subject", help="한 섹션을 고를 과목")
    parser.add_argument("--section", help="한 섹션을 고를 영역")
    parser.add_argument("--subjects", nargs="+", help="실행할 과목 또는 탐구 영역 목록")
    parser.add_argument("--question-numbers", nargs="+", type=int, help="문항별 실행에서 고를 문제 번호")
    parser.add_argument("--benchmark-all", action="store_true", help="시험의 모든 섹션 채점")
    parser.add_argument("--update", action="store_true", help="선택 범위의 기존 verified 결과도 재채점")
    parser.add_argument("--output", help="검증 결과 색인 경로 재정의")
    return parser


def _generic_main(arguments: Sequence[str]) -> int:
    """@description 시험 ID 기준 단일 실행 채점"""
    args = _build_parser().parse_args(list(arguments))
    if (args.subject is None) != (args.section is None):
        _build_parser().error("--subject와 --section은 함께 지정해야 합니다.")
    try:
        exam_argument = Path(args.exam).expanduser()
        exam_input = (
            load_exam(exam_argument, project_root=exam_argument.resolve().parent)
            if exam_argument.is_file()
            else args.exam
        )
        exam, mode, _run, run_path = resolve_run(
            exam_input,
            easy=args.easy,
            model_names=args.models,
        )
        verifier = build_verifier(args.config)
        print(f"검증기: {verifier.model_id} ({verifier.reasoning_effort})", flush=True)
        verified = grade_run(
            run_path,
            exam,
            verifier,
            mode=mode,
            model_names=args.models,
            targets=args.targets,
            subject=args.subject,
            section=args.section,
            subjects=args.subjects,
            benchmark_all=args.benchmark_all,
            question_numbers=args.question_numbers,
            update=args.update,
        )
        output_path = Path(args.output).expanduser().resolve() if args.output else run_path
        save_verified(verified, output_path)
        print(f"\n✓ 검증 완료: {output_path}", flush=True)
        for model_name, score in verified["score_by_model"].items():
            complete = "완료" if verified["complete_by_model"][model_name] else "미완료"
            print(f"{model_name}: {score}점 ({complete})", flush=True)
        return 0
    except (OSError, ValueError, EvaluationError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    """@description 시험 단일 실행 답안 채점"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    return _generic_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
