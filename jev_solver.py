"""@description Jev 실행기 진입점"""

from __future__ import annotations

from collections.abc import Sequence

from csat_benchmark.cli import api_main
from csat_benchmark.jev_runner import check_jev_exam, run_jev_exam


def main(argv: Sequence[str] | None = None) -> int:
    """@description Jev 시험 ID 기반 실행"""
    return api_main(
        argv,
        default_config_filename="jev_config.json",
        check_fn=check_jev_exam,
        run_fn=run_jev_exam,
    )


if __name__ == "__main__":
    raise SystemExit(main())
