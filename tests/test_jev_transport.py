"""@description Jev 요청 본문·응답 전송 계약 검증"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import Any

import pytest
import requests
from PIL import Image

from csat_benchmark.jev import JevClient, build_jev_questions, decode_jev_answer
from csat_benchmark.models import ModelConfig, Question


def _question_info(number: int, text: str) -> dict[str, Any]:
    """@description Jev 입력용 원본 문항 메타데이터 생성"""
    return {"number": number, "question_text": text}


def _config(**overrides: Any) -> ModelConfig:
    """@description Jev 전송 테스트용 모델 설정 생성"""
    values = {
        "name": "Jev 테스트",
        "api_type": "jev",
        "api_key": ["key-one", "key-two"],
        "model_id": "typesafe/jev-1.13",
        "base_url": "https://example.test/api/alpha/decisions",
    }
    values.update(overrides)
    return ModelConfig(**values)


class _FakeResponse:
    """@description Jev HTTP 응답 모의 객체"""

    def __init__(self, status_code: int, body: Any = None, text: str | None = None):
        self.status_code = status_code
        self.body = body
        self.text = text if text is not None else json.dumps(body, ensure_ascii=False)

    def json(self) -> Any:
        if isinstance(self.body, BaseException):
            raise self.body
        return self.body


def _choice_answer(choice: str) -> dict[str, Any]:
    """@description 테스트용 Jev 선택 응답 생성"""
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": {choice: 0.1},
        "confidence": 0.0,
    }


def _successful_response() -> _FakeResponse:
    """@description 이미지 전송 테스트용 유효 응답 생성"""
    return _FakeResponse(
        200,
        {
            "answers": {"q1": _choice_answer("2")},
            "usage": {"input_tokens": 11, "output_tokens": 4},
        },
    )


def test_build_jev_questions_encodes_objective_and_short_math_answers():
    """@description 객관식·수학 주관식 기준과 자리별 지시 생성 확인"""
    objective_text = "1. 보기 중 알맞은 것을 고르세요.\n① 첫째\n② 둘째\n③ 셋째\n④ 넷째\n⑤ 다섯째"
    questions = build_jev_questions(
        "수학",
        [
            _question_info(1, objective_text),
            _question_info(16, "16. 값을 구하시오."),
        ],
    )

    assert questions["q1"] == {
        "type": "choice",
        "instructions": "시험지 1번 문항의 정답 선택지를 고르세요.",
        "criteria": {str(choice): f"{choice}번 선택지" for choice in range(1, 6)},
    }
    for place, place_name in (
        ("hundreds", "백의 자리"),
        ("tens", "십의 자리"),
        ("units", "일의 자리"),
    ):
        instruction = questions[f"q16_{place}"]["instructions"]
        assert "시험지 16번" in instruction
        assert place_name in instruction
        assert "왼쪽을 0으로 채우세요" in instruction
        assert questions[f"q16_{place}"]["criteria"] == {
            str(digit): str(digit) for digit in range(10)
        }


@pytest.mark.parametrize("padded_answer", ["007", "042", "128", "999"])
def test_decode_jev_answer_preserves_digit_places(padded_answer: str):
    """@description 세 자리 응답의 앞자리 0과 수치 디코드 확인"""
    answers = {
        f"q16_{place}": _choice_answer(digit)
        for place, digit in zip(("hundreds", "tens", "units"), padded_answer)
    }

    assert decode_jev_answer(answers, 16) == int(padded_answer)


def test_decode_jev_answer_accepts_objective_choice_and_rejects_invalid_groups():
    """@description 객관식 번호와 누락·범위 초과·충돌 응답 거부 확인"""
    assert decode_jev_answer({"q7": _choice_answer("5")}, 7) == 5

    with pytest.raises(ValueError, match="불완전합니다"):
        decode_jev_answer({"q7_hundreds": _choice_answer("0")}, 7)
    with pytest.raises(ValueError, match="잘못되었습니다"):
        decode_jev_answer({"q7": _choice_answer("0")}, 7)
    with pytest.raises(ValueError, match="함께 있습니다"):
        decode_jev_answer(
            {
                "q7": _choice_answer("1"),
                "q7_hundreds": _choice_answer("0"),
                "q7_tens": _choice_answer("0"),
                "q7_units": _choice_answer("1"),
            },
            7,
        )
    with pytest.raises(ValueError, match="응답 필드"):
        decode_jev_answer(
            {"q7": _choice_answer("1"), "q7_extra": _choice_answer("2")},
            7,
        )


def test_send_questions_preserves_prepared_state_usage_and_raw_response(monkeypatch):
    """@description Jev 요청 상태·지시·인증·응답 원문·사용량 유지 확인"""
    state = "1. 원본 문항\n① 첫 번째\n② 두 번째\n③ 세 번째\n④ 네 번째\n⑤ 다섯 번째"
    original_metadata = [_question_info(1, state)]
    response_data = {
        "model": "typesafe/jev-1.13",
        "answers": {"q1": _choice_answer("2")},
        "usage": {"input_tokens": 11, "output_tokens": 4, "cost": 0.003},
        "id": "dec_123",
        "provider": "test-provider",
    }
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append((url, kwargs))
        return _FakeResponse(200, response_data)

    monkeypatch.setattr("csat_benchmark.jev.requests.post", fake_post)
    prepared_question = Question(
        number=0,
        correct_answer=987654,
        points=2,
        question_text=state,
    )
    client = JevClient(_config(), system_prompt="응답은 신중히 고르세요.")

    result = client.send_questions(
        prepared_question,
        subject="국어",
        questions=original_metadata,
    )

    assert result.success is True
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (11, 4, 15)
    assert json.loads(result.raw_response) == response_data
    assert calls[0][0] == "https://example.test/api/alpha/decisions"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer key-one"
    payload = calls[0][1]["json"]
    assert payload["model"] == "typesafe/jev-1.13"
    assert payload["state"] == state
    assert payload["questions"]["q1"]["instructions"].endswith(
        "응답은 신중히 고르세요."
    )
    assert "987654" not in json.dumps(payload, ensure_ascii=False)
    assert "correct_answer" not in json.dumps(payload, ensure_ascii=False)


def test_send_questions_preserves_other_jev_models_webp_chat_content(
    monkeypatch, tmp_path
):
    """@description 다른 Jev 모델의 기존 WebP·문자 사전 전송 보존 확인"""
    first_image_path = tmp_path / "시험지_1.png"
    first_image = Image.new("RGBA", (2, 2))
    first_image.putdata(
        [
            (20, 40, 60, 255),
            (80, 100, 120, 128),
            (140, 160, 180, 0),
            (200, 220, 240, 64),
        ]
    )
    first_image.save(first_image_path, format="PNG")
    second_image_path = tmp_path / "시험지_2.png"
    second_image = Image.new("RGB", (3, 2), (30, 50, 70))
    second_image.save(second_image_path, format="PNG")
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda _url, **kwargs: (captured.append(kwargs["json"]) or _successful_response()),
    )
    client = JevClient(
        _config(model_id="other-provider/jev-vision", supports_vision=True)
    )
    question_text = "공통 지문과 문항 본문"

    result = client.send_questions(
        Question(
            number=0,
            correct_answer=1,
            points=2,
            question_text=question_text,
            image_paths=[str(first_image_path), str(second_image_path)],
        ),
        subject="국어",
        questions=[_question_info(1, "1. 답을 고르세요.")],
    )

    assert result.success is True
    state = captured[0]["state"]
    assert [(part["type"], part.get("text")) for part in state] == [
        ("text", question_text),
        ("text", "[이미지:시험지_1]"),
        ("image_url", None),
        ("text", "[이미지:시험지_2]"),
        ("image_url", None),
    ]
    for image_part, original_image in zip(
        (state[2], state[4]),
        (first_image, second_image),
    ):
        url = image_part["image_url"]["url"]
        mime_type, encoded_data = url.removeprefix("data:").split(";base64,", 1)
        assert mime_type == "image/webp"
        assert image_part["image_url"]["detail"] == "high"
        decoded_image = Image.open(BytesIO(base64.b64decode(encoded_data)))
        assert decoded_image.size == original_image.size
        assert decoded_image.convert("RGBA").tobytes() == original_image.convert(
            "RGBA"
        ).tobytes()


def test_typesafe_jev_uses_png_images_and_string_text_in_order(monkeypatch, tmp_path):
    """@description TypeSafe Jev의 PNG·문자열 본문·순서·픽셀 보존 확인"""
    image_paths = [tmp_path / "시험지_1.png", tmp_path / "시험지_2.png"]
    original_images = [Image.new("RGBA", (400, 300)), Image.new("RGB", (300, 300))]
    original_images[0].putdata(
        [
            (20, 40, 60, 255),
            (80, 100, 120, 128),
            (140, 160, 180, 0),
            (200, 220, 240, 64),
        ]
        * (400 * 300 // 4)
    )
    original_images[1].putpixel((0, 0), (30, 50, 70))
    source_files = []
    for path, original_image in zip(image_paths, original_images):
        original_image.save(path, format="PNG")
        source_files.append(path.read_bytes())

    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda _url, **kwargs: (captured.append(kwargs["json"]) or _successful_response()),
    )
    client = JevClient(_config(model_id="typesafe/jev-1.14", supports_vision=True))
    question_text = "공통 지문과 문항 본문"

    result = client.send_questions(
        Question(
            number=0,
            correct_answer=1,
            points=2,
            question_text=question_text,
            image_paths=[str(path) for path in image_paths],
        ),
        subject="국어",
        questions=[_question_info(1, "1. 답을 고르세요.")],
    )

    assert result.success is True
    state = captured[0]["state"]
    assert [item if isinstance(item, str) else item["type"] for item in state] == [
        question_text,
        "[이미지:시험지_1]",
        "image_url",
        "[이미지:시험지_2]",
        "image_url",
    ]
    for image_part, original_image in zip((state[2], state[4]), original_images):
        url = image_part["image_url"]["url"]
        mime_type, encoded_data = url.removeprefix("data:").split(";base64,", 1)
        assert mime_type == "image/png"
        assert image_part["image_url"]["detail"] == "high"
        decoded_image = Image.open(BytesIO(base64.b64decode(encoded_data)))
        assert decoded_image.size == original_image.size
        assert decoded_image.convert("RGBA").tobytes() == original_image.convert(
            "RGBA"
        ).tobytes()
    assert [path.read_bytes() for path in image_paths] == source_files


def test_typesafe_jev_resizes_oversized_image_and_pads_minimum_side(
    monkeypatch, tmp_path
):
    """@description 초과 크기 LANCZOS 축소 및 최소 변 길이 패딩 확인"""
    image_path = tmp_path / "초장형_문항.png"
    original_image = Image.new("RGB", (3493, 534), "white")
    original_image.paste((20, 80, 140), (300, 60, 1900, 474))
    original_image.paste((220, 40, 30), (1900, 60, 3200, 474))
    original_image.save(image_path, format="PNG")
    source_file = image_path.read_bytes()
    expected_image = original_image.copy()
    expected_image.thumbnail((1568, 1568), Image.Resampling.LANCZOS)
    expected_canvas = Image.new("RGBA", (1568, 280), (255, 255, 255, 255))
    expected_canvas.paste(expected_image.convert("RGBA"), (0, 20))

    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda _url, **kwargs: (captured.append(kwargs["json"]) or _successful_response()),
    )
    client = JevClient(_config(supports_vision=True))

    result = client.send_questions(
        Question(
            number=1,
            correct_answer=1,
            points=2,
            question_text="초장형 이미지 문항",
            image_paths=[str(image_path)],
        ),
        subject="국어",
        questions=[_question_info(1, "1. 답을 고르세요.")],
    )

    assert result.success is True
    state = captured[0]["state"]
    assert state[0] == "초장형 이미지 문항"
    url = state[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    decoded_image = Image.open(BytesIO(base64.b64decode(url.partition(",")[2])))
    assert decoded_image.size == (1568, 280)
    assert decoded_image.convert("RGBA").tobytes() == expected_canvas.tobytes()
    assert image_path.read_bytes() == source_file


def test_typesafe_jev_pads_to_minimum_area_without_resizing_pixels(
    monkeypatch, tmp_path
):
    """@description 최소 변 적용 후 최소 면적까지 중앙 흰색 패딩 확인"""
    image_path = tmp_path / "작은_문항.png"
    original_image = Image.new("RGBA", (200, 200), (40, 80, 120, 180))
    original_image.putpixel((0, 0), (200, 100, 50, 255))
    original_image.save(image_path, format="PNG")
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda _url, **kwargs: (captured.append(kwargs["json"]) or _successful_response()),
    )
    client = JevClient(_config(supports_vision=True))

    result = client.send_questions(
        Question(
            number=1,
            correct_answer=1,
            points=2,
            question_text="작은 이미지 문항",
            image_paths=[str(image_path)],
        ),
        subject="국어",
        questions=[_question_info(1, "1. 답을 고르세요.")],
    )

    assert result.success is True
    url = captured[0]["state"][1]["image_url"]["url"]
    decoded_image = Image.open(BytesIO(base64.b64decode(url.partition(",")[2])))
    assert decoded_image.size == (280, 280)
    assert decoded_image.width * decoded_image.height >= 78400
    assert decoded_image.crop((40, 40, 240, 240)).tobytes() == original_image.tobytes()
    assert decoded_image.getpixel((0, 0)) == (255, 255, 255, 255)


def test_send_questions_missing_vision_image_fails_before_http(monkeypatch, tmp_path):
    """@description 누락 이미지를 HTTP 호출 전에 실패 처리"""
    calls: list[Any] = []
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    client = JevClient(_config(supports_vision=True))

    with pytest.raises(FileNotFoundError):
        client.send_questions(
            Question(
                number=1,
                correct_answer=1,
                points=2,
                question_text="본문",
                image_paths=[str(tmp_path / "없음.png")],
            ),
            subject="국어",
            questions=[_question_info(1, "본문")],
        )

    assert calls == []


def test_send_questions_text_only_model_preserves_string_state_with_image(
    monkeypatch, tmp_path
):
    """@description 이미지가 붙은 문자 전용 모델의 기존 문자열 상태 보존"""
    image_path = tmp_path / "무시.png"
    image_path.write_bytes(b"image bytes")
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda _url, **kwargs: (captured.append(kwargs["json"]) or _successful_response()),
    )
    client = JevClient(_config(supports_vision=False))
    question_text = "기존 문자 상태"

    result = client.send_questions(
        Question(
            number=1,
            correct_answer=1,
            points=2,
            question_text=question_text,
            image_paths=[str(image_path)],
        ),
        subject="국어",
        questions=[_question_info(1, question_text)],
    )

    assert result.success is True
    assert captured[0]["state"] == question_text


def test_client_uses_default_decision_endpoint_without_override():
    """@description 기본 Jev 결정 API 주소 사용 확인"""
    assert JevClient(_config(base_url=None)).api_url == (
        "https://openrouter.ai/api/alpha/decisions"
    )


@pytest.mark.parametrize(
    ("status_code", "body", "text", "failure_type"),
    [
        (503, {"error": "temporary"}, None, "http_error"),
        (200, ValueError("invalid JSON"), "not JSON", "invalid_json"),
        (200, {"model": "typesafe/jev-1.13"}, None, "invalid_answers"),
        (200, {"answers": {}}, None, "invalid_answers"),
        (200, {"answers": {"q2": _choice_answer("1")}}, None, "invalid_answers"),
        (200, {"answers": {"q1": _choice_answer("6")}}, None, "invalid_answers"),
    ],
)
def test_send_questions_marks_http_and_malformed_responses_as_technical_failure(
    monkeypatch,
    status_code: int,
    body: Any,
    text: str | None,
    failure_type: str,
):
    """@description Jev HTTP·JSON·답안 오류를 재시도 가능한 실패로 처리"""
    response = _FakeResponse(status_code, body, text)
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda *_args, **_kwargs: response,
    )
    client = JevClient(_config())

    result = client.send_questions(
        Question(number=1, correct_answer=1, points=2, question_text="본문"),
        subject="국어",
        questions=[_question_info(1, "본문")],
    )

    assert result.success is False
    assert result.answer_status == "technical_failure"
    assert result.error_details == {"failure_type": failure_type}


@pytest.mark.parametrize(
    "body",
    [
        {"answers": {"q1": _choice_answer("1")}},
        {"answers": {"q1": _choice_answer("1")}, "usage": {}},
        {
            "answers": {"q1": _choice_answer("1")},
            "usage": {"input_tokens": 1},
        },
        {
            "answers": {"q1": _choice_answer("1")},
            "usage": {"output_tokens": 1},
        },
        {
            "answers": {"q1": _choice_answer("1")},
            "usage": {"input_tokens": None, "output_tokens": 1},
        },
        {
            "answers": {"q1": _choice_answer("1")},
            "usage": {"input_tokens": 1, "output_tokens": None},
        },
    ],
)
def test_send_questions_rejects_missing_or_null_usage_counts(monkeypatch, body):
    """@description 필수 Jev 사용량·토큰 수 누락과 null을 기술 실패로 처리"""
    monkeypatch.setattr(
        "csat_benchmark.jev.requests.post",
        lambda *_args, **_kwargs: _FakeResponse(200, body),
    )
    client = JevClient(_config())

    result = client.send_questions(
        Question(number=1, correct_answer=1, points=2, question_text="본문"),
        subject="국어",
        questions=[_question_info(1, "본문")],
    )

    assert result.success is False
    assert result.answer_status == "technical_failure"
    assert result.error_details == {"failure_type": "invalid_usage"}


def test_send_questions_marks_network_errors_as_technical_failure(monkeypatch):
    """@description Jev 네트워크 예외의 재시도 가능 실패 상태 확인"""
    def fake_post(*_args: Any, **_kwargs: Any) -> None:
        raise requests.ConnectionError("연결 실패")

    monkeypatch.setattr("csat_benchmark.jev.requests.post", fake_post)
    client = JevClient(_config())

    result = client.send_questions(
        Question(number=1, correct_answer=1, points=2, question_text="본문"),
        subject="국어",
        questions=[_question_info(1, "본문")],
    )

    assert result.success is False
    assert result.answer_status == "technical_failure"
    assert result.error_details == {"failure_type": "network_error"}
