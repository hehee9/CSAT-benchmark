"""@description 공급자 PDF 요청 본문·매체 검증 계약 확인"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from csat_benchmark.models import ModelConfig, Question
from csat_benchmark.providers.requests import (
    build_anthropic_content,
    build_chat_content,
    build_responses_content,
    validate_question_media,
)


def _config(api_type: str = "openai", **overrides: Any) -> ModelConfig:
    """@description 매체 검증용 모델 설정 생성"""
    values = {
        "name": f"{api_type} 테스트",
        "api_type": api_type,
        "api_key": "test-key",
        "model_id": "test-model",
        "supports_vision": True,
        "concurrent_request_limit": 1,
    }
    values.update(overrides)
    return ModelConfig(**values)


def _question(pdf_path: Path, image_path: Path) -> Question:
    """@description PDF·이미지·본문 대표 문항 생성"""
    return Question(
        number=7,
        correct_answer=3,
        points=2,
        question_text="본문",
        image_paths=[str(image_path)],
        pdf_paths=[str(pdf_path)],
    )


def _write_png(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    """@description 테스트용 PNG 이미지 생성"""
    Image.new("RGB", size, color).save(path, format="PNG")


def test_pdf_payloads_preserve_provider_shapes_and_content_order(tmp_path: Path):
    """@description PDF 전송 본문 형식·매체 순서 확인"""
    pdf_path = tmp_path / "문항.pdf"
    image_path = tmp_path / "문항.png"
    pdf_path.write_bytes(b"pdf-bytes")
    image_path.write_bytes(b"image-bytes")
    question = _question(pdf_path, image_path)
    pdf_data = base64.b64encode(b"pdf-bytes").decode("ascii")
    image_data = base64.b64encode(b"image-bytes").decode("ascii")

    assert build_chat_content(question) == [
        {
            "type": "file",
            "file": {
                "filename": "문항.pdf",
                "file_data": f"data:application/pdf;base64,{pdf_data}",
            },
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_data}"},
        },
        {"type": "text", "text": "본문"},
    ]
    assert build_responses_content(question) == [
        {
            "type": "input_file",
            "filename": "문항.pdf",
            "file_data": f"data:application/pdf;base64,{pdf_data}",
        },
        {
            "type": "input_image",
            "image_url": f"data:image/png;base64,{image_data}",
        },
        {"type": "input_text", "text": "본문"},
    ]
    assert build_anthropic_content(question) == [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_data,
            },
        },
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_data,
            },
        },
        {"type": "text", "text": "본문"},
    ]


def test_anthropic_many_images_resize_oversized_payloads_in_order(tmp_path: Path):
    """@description Anthropic 21개 이미지의 초과 크기 조정·순서·원본 보존 확인"""
    image_paths = [tmp_path / f"문항_{index:02d}.png" for index in range(21)]
    _write_png(image_paths[0], (320, 240), (1, 2, 3))
    _write_png(image_paths[1], (3000, 1500), (4, 5, 6))
    for index, path in enumerate(image_paths[2:], start=2):
        _write_png(path, (320, 240), (index, index, index))

    original_small = image_paths[0].read_bytes()
    original_oversized = image_paths[1].read_bytes()
    question = Question(
        number=0,
        correct_answer=0,
        points=2,
        question_text="본문",
        image_paths=[str(path) for path in image_paths],
    )

    content = build_anthropic_content(question)
    image_indexes = [
        index for index, part in enumerate(content) if part["type"] == "image"
    ]

    assert len(image_indexes) == 21
    assert [
        content[index - 1]["text"] for index in image_indexes
    ] == [f"[이미지:{path.stem}]" for path in image_paths]
    assert content[-1] == {"type": "text", "text": "본문"}

    small_source = content[image_indexes[0]]["source"]
    assert base64.b64decode(small_source["data"]) == original_small
    assert small_source["media_type"] == "image/png"

    oversized_source = content[image_indexes[1]]["source"]
    assert oversized_source["media_type"] == "image/png"
    with Image.open(BytesIO(base64.b64decode(oversized_source["data"]))) as image:
        assert image.format == "PNG"
        assert image.size == (2000, 1000)
    assert image_paths[0].read_bytes() == original_small
    assert image_paths[1].read_bytes() == original_oversized


def test_anthropic_twenty_images_leave_oversized_payload_unchanged(tmp_path: Path):
    """@description Anthropic 20개 이미지 경계에서 초과 크기 원본 유지 확인"""
    image_paths = [tmp_path / f"문항_{index:02d}.png" for index in range(20)]
    _write_png(image_paths[0], (3000, 1500), (1, 2, 3))
    for index, path in enumerate(image_paths[1:], start=1):
        _write_png(path, (320, 240), (index, index, index))

    original_oversized = image_paths[0].read_bytes()
    question = Question(
        number=0,
        correct_answer=0,
        points=2,
        question_text="본문",
        image_paths=[str(path) for path in image_paths],
    )

    content = build_anthropic_content(question)
    oversized_source = content[1]["source"]

    assert base64.b64decode(oversized_source["data"]) == original_oversized
    with Image.open(BytesIO(base64.b64decode(oversized_source["data"]))) as image:
        assert image.size == (3000, 1500)


@pytest.mark.parametrize(
    ("media_field", "api_type", "supports_vision", "batch", "message"),
    [
        ("image_paths", "openai", False, False, "이미지"),
        ("pdf_paths", "deepseek", True, False, "PDF"),
        ("pdf_paths", "openai", False, False, "PDF"),
        ("audio_paths", "openai", True, False, "오디오"),
        ("video_paths", "openai", True, False, "동영상"),
        ("pdf_paths", "google", True, True, "배치"),
        ("audio_paths", "google", True, True, "배치"),
        ("video_paths", "google", True, True, "배치"),
    ],
)
def test_validate_question_media_rejects_unsupported_media(
    media_field: str,
    api_type: str,
    supports_vision: bool,
    batch: bool,
    message: str,
):
    """@description 공급자·배치 미지원 매체 거부 확인"""
    question = Question(
        number=1,
        correct_answer=1,
        points=2,
        **{media_field: [f"문항.{media_field.removesuffix('_paths')}"]},
    )

    with pytest.raises(ValueError, match=message):
        validate_question_media(
            question,
            _config(api_type, supports_vision=supports_vision),
            batch=batch,
        )


def test_validate_question_media_allows_supported_media():
    """@description Google 단건·OpenAI PDF 지원 매체 통과 확인"""
    google_question = Question(
        number=1,
        correct_answer=1,
        points=2,
        image_paths=["문항.png"],
        pdf_paths=["문항.pdf"],
        audio_paths=["문항.mp3"],
        video_paths=["문항.mp4"],
    )
    validate_question_media(google_question, _config("google"))

    openai_question = Question(
        number=1,
        correct_answer=1,
        points=2,
        pdf_paths=["문항.pdf"],
    )
    validate_question_media(openai_question, _config("openai"))
