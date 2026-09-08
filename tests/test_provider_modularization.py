"""@description 공용 공급자 요청 생성기·공개 진입점 계약 검증"""

from __future__ import annotations

import ast
from pathlib import Path

from csat_benchmark.models import ModelConfig, Question
from csat_benchmark.providers.requests import (
    build_anthropic_params,
    build_chat_body,
    build_google_request,
    build_responses_body,
)


def _model_config() -> ModelConfig:
    """@description 모듈화 요청 테스트용 모델 설정 생성"""
    return ModelConfig(
        name="모의 모델",
        api_type="openai",
        api_key="test-key",
        model_id="gpt-6-sol",
        max_tokens=128,
        concurrent_request_limit=1,
    )


def test_shared_payload_builders_keep_provider_specific_shapes(tmp_path: Path):
    """@description 공용 요청 생성기 공급자별 전송 본문 구조 확인"""
    image_path = tmp_path / "문항.png"
    image_path.write_bytes(b"fake-image")
    question = Question(
        number=3,
        correct_answer=2,
        points=2,
        question_text="본문",
        image_paths=[str(image_path)],
    )
    config = _model_config()

    chat_body = build_chat_body(
        question,
        config,
        system_prompt="공통 안내",
        supports_vision=True,
        skip_missing=False,
    )
    assert chat_body["messages"][0] == {"role": "system", "content": "공통 안내"}
    assert chat_body["messages"][1]["content"][-1] == {"type": "text", "text": "본문"}

    responses_body = build_responses_body(
        question,
        config,
        image_format="base64_source",
        supports_vision=True,
        skip_missing=False,
    )
    assert responses_body["input"][0]["role"] == "user"
    assert responses_body["input"][0]["content"][-1] == {
        "type": "input_text",
        "text": "본문",
    }

    anthropic_body = build_anthropic_params(
        question,
        config,
        system_prompt="공통 안내",
        supports_vision=True,
        skip_missing=False,
    )
    assert anthropic_body["system"] == "공통 안내"
    assert anthropic_body["messages"][0]["content"][-1] == {"type": "text", "text": "본문"}

    google_request = build_google_request(question, config, supports_vision=True)
    assert len(google_request["contents"]) == 1
    assert google_request["contents"][0]["role"] == "user"
    assert google_request["contents"][0]["parts"][0] == {"text": "본문"}
    assert "inlineData" in google_request["contents"][0]["parts"][1]


def test_public_entrypoints_import_modern_modules_without_legacy_dispatch():
    """@description 공개 루트 진입점 레거시 import·전역 재내보내기 제거 확인"""
    project_root = Path(__file__).resolve().parents[1]
    for name in ("api_solver.py", "batch_solver.py", "verify_answers.py"):
        source = (project_root / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        assert "csat_benchmark.legacy" not in source
        assert not any(
            isinstance(node, ast.ImportFrom) and node.module == "csat_benchmark.legacy"
            for node in imports
        )
        assert "globals().update" not in source
