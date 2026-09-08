"""답안 추출기와 단일 생성 채점 정책 계약 검증."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from csat_benchmark.grading import extractor
from csat_benchmark.grading.single import verify_hard_single_result, verify_single_result


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


class _FakeResponses:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def create(self, **payload):
        self.calls.append(payload)
        return _FakeResponse(self.outputs.pop(0))


class _FakeOpenAI:
    instances: list["_FakeOpenAI"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.responses = _FakeResponses([])
        self.__class__.instances.append(self)


def test_answer_verifier_payloads_truncation_and_prompt_contract(monkeypatch):
    """일반·섹션 추출기의 요청 구조와 응답 축약 정책 검증."""
    _FakeOpenAI.instances.clear()
    monkeypatch.setattr(extractor, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(extractor, "OPENAI_AVAILABLE", True)
    verifier = extractor.AnswerVerifier(
        "secret",
        system_prompt="CUSTOM_SINGLE",
        model_id="extractor-model",
        reasoning_effort="high",
        base_url="https://example.test/v1",
    )
    verifier.client.responses.outputs.extend(
        [
            json.dumps({"llm_answer": 3}),
            json.dumps(
                {"answers": [{"question_number": 1, "correct_answer": 3, "llm_answer": 3}]}
            ),
        ]
    )
    raw_response = "H" * 500 + "M" * 1200 + "T" * 500
    single_question_text = """1. 이 문항의 본문은 채점 입력에서 제외해야 합니다.
  ① 첫 번째 선택지
    첫 번째 선택지의 이어지는 줄
  ② 두 번째 선택지
  ③ 세 번째 선택지
    세 번째 선택지의 이어지는 줄
  ④ 네 번째 선택지
  ⑤ 다섯 번째 선택지
"""
    assert verifier.verify_answer(raw_response, 3, 1, single_question_text) == 3
    hard_question_infos = [
        {
            "number": 1,
            "correct_answer": 3,
            "question_text": """9. 표 앞의 문항 본문은 채점 입력에서 제외해야 합니다.
  | 선택지 | 설명 |
  | :--- | ---: |
  | ① | 첫 번째 |
  | ② | 두 번째 |
  | ③ | 세 번째 |
  | ④ | 네 번째 |
  | ⑤ | 다섯 번째 |
""",
        },
        {
            "number": 2,
            "correct_answer": 4,
            "question_text": """35. 바깥 본문은 제외합니다.
```
① 지문 안에 포함된 첫 번째 문장
② 지문 안에 포함된 두 번째 문장
③ 지문 안에 포함된 세 번째 문장
④ 지문 안에 포함된 네 번째 문장
⑤ 지문 안에 포함된 다섯 번째 문장
```
""",
        },
        {
            "number": 3,
            "correct_answer": 2,
            "question_text": """38. 삽입 위치를 묻는 문항의 바깥 본문입니다.
```
주어진 문장
```

본문의 첫 부분 ( ① ) 본문 중간 ( ② )
본문의 다음 부분 ( ③ ) 본문의 뒷부분 ( ④ ) 끝 ( ⑤ )
""",
        },
        {
            "number": 4,
            "correct_answer": 6,
            "question_text": "39. 주관식 문항 본문은 선택지 없이 비워 둡니다.",
        },
        {
            "number": 5,
            "correct_answer": 1,
            "question_text": """4. 그림과 대화의 일치 여부를 묻는 문항의 본문입니다.
```
대화 원문
```

[이미지: 04_01]

① ② ③ ④ ⑤
""",
        },
    ]
    assert verifier.verify_hard_answers(
        "원문 전체", hard_question_infos
    ) == [{"question_number": 1, "correct_answer": 3, "llm_answer": 3}]

    single_call, hard_call = verifier.client.responses.calls
    assert _FakeOpenAI.instances[0].kwargs == {
        "api_key": "secret",
        "base_url": "https://example.test/v1",
    }
    assert single_call["model"] == "extractor-model"
    assert single_call["reasoning"] == {"effort": "high"}
    assert single_call["input"][0]["content"][0]["text"] == "CUSTOM_SINGLE"
    single_user = single_call["input"][1]["content"][0]["text"]
    assert "<question>" not in single_user
    assert "이 문항의 본문은 채점 입력에서 제외해야 합니다." not in single_user
    assert "  ① 첫 번째 선택지\n    첫 번째 선택지의 이어지는 줄" in single_user
    assert "  ⑤ 다섯 번째 선택지" in single_user
    assert "H" * 500 in single_user
    assert "T" * 500 in single_user
    assert "M" * 1200 not in single_user
    assert hard_call["input"][0]["content"][0]["text"] == extractor.AnswerVerifier.HARD_SYSTEM_PROMPT
    hard_user = hard_call["input"][1]["content"][0]["text"]
    assert "원문 전체" in hard_user
    assert "<question_1_text>" not in hard_user
    assert "표 앞의 문항 본문은 채점 입력에서 제외해야 합니다." not in hard_user
    assert "  | 선택지 | 설명 |\n  | :--- | ---: |\n  | ① | 첫 번째 |" in hard_user
    assert "```\n① 지문 안에 포함된 첫 번째 문장" in hard_user
    assert "35. 바깥 본문은 제외합니다." not in hard_user
    assert "```\n주어진 문장\n```\n\n본문의 첫 부분 ( ① )" in hard_user
    assert "38. 삽입 위치를 묻는 문항의 바깥 본문입니다." not in hard_user
    assert "<question_4_choices>\n\n</question_4_choices>" in hard_user
    assert "39. 주관식 문항 본문은 선택지 없이 비워 둡니다." not in hard_user
    assert "<question_5_choices>\n① ② ③ ④ ⑤\n</question_5_choices>" in hard_user
    assert "[이미지: 04_01]" not in hard_user


def test_answer_verifier_parse_failure_returns_none(monkeypatch):
    """추출기 JSON 파싱 실패 시 None 보존."""
    monkeypatch.setattr(extractor, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(extractor, "OPENAI_AVAILABLE", True)
    verifier = extractor.AnswerVerifier("secret")
    verifier.client.responses.outputs.append("not-json")
    assert verifier.verify_answer("응답", 1, 1) is None
    assert len(verifier.client.responses.calls) == 1


@dataclass
class _SequenceVerifier:
    answers: list[object]
    calls: int = 0

    def verify_answer(self, raw_response, correct_answer, question_number, question_text):
        self.calls += 1
        return self.answers.pop(0)


@dataclass
class _HardSequenceVerifier:
    outputs: list[object]
    calls: list[list[int]] | None = None

    def __post_init__(self):
        self.calls = []

    def verify_hard_answers(self, raw_response, question_infos):
        self.calls.append([info["number"] for info in question_infos])
        return self.outputs.pop(0)


def _result(**updates):
    result = {
        "question_number": 1,
        "model_name": "모델",
        "success": True,
        "raw_response": "응답",
        "answer_status": None,
        "provider_stop_reason": None,
    }
    result.update(updates)
    return result


def _info(number=1, correct=1):
    return {"number": number, "correct_answer": correct, "points": 2, "question_text": "본문"}


def _hard_answer(number, answer, correct=1):
    return {"question_number": number, "correct_answer": correct, "llm_answer": answer}


def test_single_two_checks_and_conditional_third_match_legacy():
    """첫 두 추출 일치 시 종료하고 불일치 시 세 번째 추출을 수행."""
    verifier = _SequenceVerifier([2, 2])
    result, manual = verify_single_result(verifier, _result(), _info(), 1, Path.cwd())
    assert verifier.calls == 2
    assert result.extracted_answer == 2
    assert manual is None

    verifier = _SequenceVerifier([1, 2, None])
    result, manual = verify_single_result(verifier, _result(), _info(), 1, Path.cwd())
    assert verifier.calls == 3
    assert result.extracted_answer == 1
    assert result.needs_manual_review is True
    assert manual == ("모델", 1, [1, 2, None])


def test_hard_missing_map_retries_only_disputed_questions():
    """hard 추출 매핑에서 누락 문항만 세 번째 검증 대상으로 선택."""
    verifier = _HardSequenceVerifier(
        [
            [_hard_answer(1, 1), _hard_answer(2, 2, 2)],
            [_hard_answer(1, 1), _hard_answer(2, 3, 2)],
            [_hard_answer(2, 2, 2)],
        ]
    )
    results, manual = verify_hard_single_result(
        verifier, _result(question_number=0), [_info(1), _info(2, 2)], 1
    )
    assert verifier.calls == [[1, 2], [1, 2], [2]]
    assert {item.question_number: item.extracted_answer for item in results} == {1: 1, 2: 2}
    assert manual == []


@pytest.mark.parametrize(
    ("status", "stop_reason", "expected_answer"),
    [("refusal", "refusal", -2), ("no_answer", None, -1)],
)
def test_single_statuses_do_not_change_result_shape(status, stop_reason, expected_answer):
    """거부·무응답 결과의 기존 답안 상태와 sentinel 보존."""
    verifier = _SequenceVerifier([expected_answer, expected_answer])
    result, manual = verify_single_result(
        verifier,
        _result(answer_status=status, provider_stop_reason=stop_reason, raw_response="응답"),
        _info(),
        1,
        Path.cwd(),
    )
    if status == "refusal":
        assert verifier.calls == 0
    else:
        assert verifier.calls == 2
    assert result.extracted_answer == expected_answer
    assert result.answer_status == status
    assert manual is None
