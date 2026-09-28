"""@description 저장된 Jev 답안을 검증 결과 형식으로 채점"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from csat_benchmark.evaluation import EvaluationError, grade_run
from csat_benchmark.jev_grading import verify_jev_section_result, verify_jev_single_result
from verify_answers import _generic_main


def _grade_jev(args: Any, exam: Any, mode: Any, run: dict[str, Any], run_path: Path) -> dict[str, Any]:
    """@description 저장 실행의 Jev 모델만 결정적으로 채점"""
    jev_models = [
        model["name"]
        for model in run["selected_models"]
        if model.get("api_type") == "jev"
    ]
    if args.models is not None:
        non_jev_models = set(args.models) - set(jev_models)
        if non_jev_models:
            raise EvaluationError(
                f"Jev 채점은 Jev 모델만 지원합니다: {', '.join(sorted(non_jev_models))}"
            )

    return grade_run(
        run_path,
        exam,
        None,
        mode=mode,
        model_names=args.models,
        default_model_names=jev_models if args.models is None else None,
        targets=args.targets,
        subject=args.subject,
        section=args.section,
        subjects=args.subjects,
        benchmark_all=args.benchmark_all,
        question_numbers=args.question_numbers,
        update=args.update,
        single_result_extractor=verify_jev_single_result,
        section_result_extractor=verify_jev_section_result,
        grading_description="Jev 저장 응답 직접 채점",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """@description 시험 단일 실행 Jev 결과 채점"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    return _generic_main(
        arguments,
        parser_description="시험 단일 실행 Jev 답안 채점",
        config_default="jev_config.json",
        config_help="Jev 채점에서는 읽지 않는 설정 경로",
        grade_handler=_grade_jev,
    )


if __name__ == "__main__":
    raise SystemExit(main())
