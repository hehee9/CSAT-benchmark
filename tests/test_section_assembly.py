"""@description hard 섹션 공통 자료·이미지 식별자 조립 계약 확인"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from PIL import Image

from csat_benchmark.models import ModelConfig, Question
from csat_benchmark.providers import google as google_provider
from csat_benchmark.providers.base import APIClient
from csat_benchmark.providers.requests import (
    build_anthropic_params,
    build_chat_body,
    build_google_request,
    build_hard_section_text_blocks,
    build_responses_body,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _question(number: int, text: str) -> Question:
    """@description 인라인 섹션 대표 문항 생성"""
    return Question(number=number, correct_answer=1, points=2, question_text=text)


def _question_from_file(path: str, number: int) -> Question:
    """@description 실제 문제 파일 기반 대표 문항 생성"""
    return Question(
        number=number,
        correct_answer=1,
        points=2,
        question_path=str(PROJECT_ROOT / path),
    )


def _assert_question_numbers_once(text: str, numbers: list[int]) -> None:
    """@description 조립 결과 문항 번호·순서 확인"""
    matches = [int(number) for number in re.findall(r"(?m)^(\d+)\.\s", text)]
    assert matches == numbers


def test_current_unmae_shared_prefix_is_retained_once():
    """@description 실제 언매 40~43 공통 지문 단일 조립 확인"""
    paths = [f"problems/국어/언매/{number}.txt" for number in range(40, 44)]
    if not all((PROJECT_ROOT / path).is_file() for path in paths):
        pytest.skip("문제 원문이 없는 환경에서는 실제 자료 검증을 건너뜁니다.")

    blocks = build_hard_section_text_blocks(
        [_question_from_file(path, number) for number, path in zip(range(40, 44), paths)]
    )
    assembled = "\n\n---\n\n".join(blocks)

    assert assembled.count("[40～43]") == 1
    _assert_question_numbers_once(assembled, [40, 41, 42, 43])


def test_shared_prefix_comparison_ignores_only_blankline_differences():
    """@description 공통 지문 비교 시 행 끝 공백·빈 줄 차이만 정규화 확인"""
    shared_prefix_a = "[40～43] 공통 지문\n\n첫 번째 문단\n\n두 번째 문단"
    shared_prefix_b = "[40～43] 공통 지문\n\n\n첫 번째 문단  \n\n\n두 번째 문단"
    questions = [
        _question(40, f"{shared_prefix_a}\n\n40. 첫 질문\n① 선택지"),
        _question(41, f"{shared_prefix_b}\n\n41. 둘째 질문\n① 선택지"),
    ]

    blocks = build_hard_section_text_blocks(questions)
    assembled = "\n\n---\n\n".join(blocks)

    assert assembled.count("[40～43] 공통 지문") == 1
    assert "첫 번째 문단  " not in assembled
    _assert_question_numbers_once(assembled, [40, 41])


def test_current_english_listening_transcript_is_retained_once():
    """@description 실제 영어 16~17 공통 듣기 대본 단일 조립 확인"""
    paths = [f"problems/영어/{number}.txt" for number in (16, 17)]
    if not all((PROJECT_ROOT / path).is_file() for path in paths):
        pytest.skip("문제 원문이 없는 환경에서는 실제 자료 검증을 건너뜁니다.")

    blocks = build_hard_section_text_blocks(
        [_question_from_file(path, number) for number, path in zip((16, 17), paths)]
    )
    assembled = "\n\n---\n\n".join(blocks)

    assert assembled.count("W: Hello, students.") == 1
    assert assembled.count("공통 자료 [16～17]") == 1
    _assert_question_numbers_once(assembled, [16, 17])


@pytest.mark.parametrize(
    "material",
    [
        "```\n공통 듣기 대본\n두 번째 줄\n```",
        "| 항목 | 값 |\n| --- | --- |\n| 공통 | 자료 |",
    ],
)
def test_adjacent_identical_structured_material_moves_to_one_labeled_block(material: str):
    """@description 인접 문항의 동일 fenced·표 자료 단일 블록 이동 확인"""
    questions = [
        _question(4, f"4. 첫 번째 고유 질문\n\n{material}\n\n① 첫 선택지\n② 둘째 선택지"),
        _question(5, f"5. 두 번째 고유 질문\n\n{material}\n\n① 다른 첫 선택지\n② 다른 둘째 선택지"),
    ]

    assembled = "\n\n---\n\n".join(build_hard_section_text_blocks(questions))

    assert assembled.count("공통 자료 (문항 4～5)") == 1
    assert assembled.count("공통 듣기 대본") == 1 or assembled.count("| 공통 | 자료 |") == 1
    assert "4. 첫 번째 고유 질문" in assembled
    assert "5. 두 번째 고유 질문" in assembled
    _assert_question_numbers_once(assembled, [4, 5])


def test_current_social_culture_questions_keep_different_materials():
    """@description 실제 사회문화 4·5 서로 다른 자료 보존 확인"""
    paths = ["problems/탐구/사회문화/4.txt", "problems/탐구/사회문화/5.txt"]
    if not all((PROJECT_ROOT / path).is_file() for path in paths):
        pytest.skip("문제 원문이 없는 환경에서는 실제 자료 검증을 건너뜁니다.")

    blocks = build_hard_section_text_blocks(
        [_question_from_file(path, number) for number, path in zip((4, 5), paths)]
    )
    assembled = "\n\n---\n\n".join(blocks)

    assert "| 문화의 속성 | 부각된 사례 |" in assembled
    assert "연구자 갑은 요즘 청소년들이 게임을 하지 않으면" in assembled
    _assert_question_numbers_once(assembled, [4, 5])


def test_near_identical_structured_material_is_not_removed():
    """@description 내용이 다른 인접 구조 자료 보존 확인"""
    questions = [
        _question(4, "4. 첫 질문\n\n```\n자료 A\n```\n\n① 선택지"),
        _question(5, "5. 둘째 질문\n\n```\n자료 B\n```\n\n① 선택지"),
    ]

    assembled = "\n\n---\n\n".join(build_hard_section_text_blocks(questions))

    assert assembled.count("자료 A") == 1
    assert assembled.count("자료 B") == 1
    assert "공통 자료 (문항 4～5)" not in assembled
    _assert_question_numbers_once(assembled, [4, 5])


def _model_config(**overrides: Any) -> ModelConfig:
    """@description 섹션 매체 요청 테스트용 모델 설정 생성"""
    values = {
        "name": "섹션 테스트 모델",
        "api_type": "openai",
        "api_key": "test-key",
        "model_id": "test-model",
        "max_tokens": 128,
        "concurrent_request_limit": 1,
    }
    values.update(overrides)
    return ModelConfig(**values)


def _image_paths(tmp_path: Path) -> list[Path]:
    """@description 파일명 식별자 검증용 이미지 생성"""
    paths = [tmp_path / "40_01.png", tmp_path / "40_02.png"]
    for index, path in enumerate(paths, start=1):
        Image.new("RGB", (index, index), (index, index, index)).save(path)
    return paths


def _provider_content_builders() -> list[tuple[str, Callable[[Question, ModelConfig], list[dict[str, Any]]]]]:
    """@description 공급자별 사용자 콘텐츠 추출기 제공"""
    return [
        ("chat", lambda question, config: build_chat_body(question, config)["messages"][0]["content"]),
        ("responses", lambda question, config: build_responses_body(question, config)["input"][0]["content"]),
        ("anthropic", lambda question, config: build_anthropic_params(question, config)["messages"][0]["content"]),
        ("google", lambda question, config: build_google_request(question, config)["contents"][0]["parts"]),
    ]


def test_section_provider_payloads_label_each_image_in_order(tmp_path: Path):
    """@description 단건 공급자별 synthetic section 이미지 식별자 정렬 확인"""
    paths = _image_paths(tmp_path)
    question = Question(
        number=0,
        correct_answer=0,
        points=4,
        question_text="조립된 섹션 본문",
        image_paths=[str(path) for path in paths],
    )

    for provider_name, build_content in _provider_content_builders():
        content = build_content(question, _model_config())
        image_indexes = [
            index
            for index, part in enumerate(content)
            if part.get("type") in {"image_url", "input_image", "image"}
            or "inlineData" in part
            or "inline_data" in part
        ]
        assert len(image_indexes) == 2, provider_name
        for image_index, path in zip(image_indexes, paths):
            caption = content[image_index - 1]
            expected = f"[이미지:{path.stem}]"
            assert caption.get("text") == expected, provider_name
        assert any(part.get("text") == "조립된 섹션 본문" for part in content)


def test_merged_section_image_has_ordered_filename_caption(tmp_path: Path):
    """@description 병합 이미지 위·아래 파일명 매핑 문구 확인"""
    paths = _image_paths(tmp_path)
    question = Question(
        number=0,
        correct_answer=0,
        points=4,
        question_text="조립된 섹션 본문",
        image_paths=[str(path) for path in paths],
    )

    content = build_chat_body(
        question,
        _model_config(merge_multiple_images=True),
    )["messages"][0]["content"]
    image_indexes = [index for index, part in enumerate(content) if part["type"] == "image_url"]

    assert len(image_indexes) == 1
    caption = content[image_indexes[0] - 1]["text"]
    assert caption == "[이미지:40_01 (위에서부터 1), 40_02 (위에서부터 2)]"


def test_google_direct_sdk_paths_label_synthetic_section_images(tmp_path: Path):
    """@description Google modern·legacy SDK 이미지 식별자 전달 확인"""
    paths = _image_paths(tmp_path)
    question = Question(
        number=0,
        correct_answer=0,
        points=4,
        question_text="조립된 섹션 본문",
        image_paths=[str(path) for path in paths],
    )
    config = _model_config(api_type="google")
    captured: list[list[Any]] = []

    class FakeModels:
        def generate_content_stream(self, **kwargs: Any):
            captured.append(kwargs["contents"])
            return iter([SimpleNamespace(text="답", usage_metadata=None)])

    client = google_provider.GoogleClient.__new__(google_provider.GoogleClient)
    APIClient.__init__(client, config)
    client.use_vertex = False
    client._current_key = "test-key"
    client.use_new_sdk = True
    client.model_id = config.model_id
    client._uploaded_files = {}
    client.client = SimpleNamespace(models=FakeModels())
    client._request_and_collect(question)
    modern_content = captured[-1]

    assert modern_content[1] == "[이미지:40_01]"
    assert modern_content[3] == "[이미지:40_02]"
    assert isinstance(modern_content[2], Image.Image)
    assert isinstance(modern_content[4], Image.Image)

    class FakeLegacyClient:
        def generate_content(self, content: list[Any], **kwargs: Any):
            captured.append(content)
            return iter([SimpleNamespace(text="답", usage_metadata=None)])

    client.use_new_sdk = False
    client.client = FakeLegacyClient()
    client._request_and_collect(question)
    legacy_content = captured[-1]

    assert legacy_content[1] == "[이미지:40_01]"
    assert legacy_content[3] == "[이미지:40_02]"
