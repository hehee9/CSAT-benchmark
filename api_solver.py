"""@description 시험 매니페스트 기반 API 실행 진입점"""

from __future__ import annotations

from collections.abc import Sequence

from csat_benchmark.cli import api_main


def main(argv: Sequence[str] | None = None) -> int:
    """@description 시험 ID 기반 API 실행"""
    return api_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
