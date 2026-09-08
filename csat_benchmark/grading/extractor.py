"""@description LLM 응답 답안 추출 검증기 구현"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


_OPTION_MARKERS = "①②③④⑤"
_OPTION_LINE_PATTERN = re.compile(r"^[ \t]*[①②③④⑤](?=[ \t]|$)")
_COMPACT_OPTION_LINE_PATTERN = re.compile(r"^[ \t]*①[ \t]*②[ \t]*③[ \t]*④[ \t]*⑤[ \t]*$")
_FENCE_LINE_PATTERN = re.compile(r"^[ \t]*```")
_TABLE_SEPARATOR_CELL_PATTERN = re.compile(r"^:?-{3,}:?$")
_INSERTION_SLOT_PATTERNS = {
    marker: re.compile(rf"\(\s*{re.escape(marker)}\s*\)")
    for marker in _OPTION_MARKERS
}


class AnswerVerifier:
    """@description OpenAI Responses API 기반 답안 추출 검증기"""

    MODEL_ID = "gpt-5.6-terra"
    REASONING_EFFORT = "low"

    RESPONSE_TRUNCATION_THRESHOLD = 2000
    RESPONSE_TRUNCATION_HEAD = 500
    RESPONSE_TRUNCATION_TAIL = 500
    RESPONSE_TRUNCATION_SEPARATOR = "\n...\n"

    # 시스템 프롬프트(사용자 수정 가능)
    SYSTEM_PROMPT = """당신은 LLM의 응답에서 결과물을 추출/요약하는 전문가입니다.
현재 당신의 업무는 **LLM의 문제 풀이 결과에서 최종 응답을 추출**하는 것입니다.

예시:
- LLM: "이 문제를 풀어보겠습니다. 보기를 확인하면... 따라서 정답은 ③ 입니다."
- 추출 결과: 3

추출 결과는 항상 정수여야 합니다. 최종 정답을 여러 개 내놓거나 답을 구하지 못한 경우에는 **-1**을 반환하십니다.
객관식 문제에서는 LLM이 제시한 최종 값이나 내용을 선택지와 대조하여 일치하는 선택지 번호를 반환합니다. 선택지 자체가 숫자여도 값 자체가 아닌 그 값에 해당하는 선택지 번호를 반환합니다.
주관식 문제에서는 LLM이 제시한 정수 답을 그대로 반환합니다.

### 출력 구조
당신은 다음 구조에 따라 결과물을 반환해야 합니다.
```
{
  correct_answer: int,
  llm_answer: int
}
```
"""

    HARD_SYSTEM_PROMPT = """당신은 LLM의 응답에서 결과물을 추출/요약하는 전문가입니다.
현재 당신의 업무는 **LLM의 문제 풀이 결과에서 문항별 최종 응답들을 추출**하는 것입니다.

예시:
- LLM: "35번은 ②, 36번은 ⑤입니다."
- 추출 결과: [{"question_number": 35, "correct_answer": 2, "llm_answer": 2}, {"question_number": 36, "correct_answer": 5, "llm_answer": 5}]

추출 결과의 llm_answer는 항상 정수여야 합니다. 특정 문항의 최종 정답을 여러 개 내놓거나 답을 구하지 못한 경우에는 해당 문항의 llm_answer로 **-1**을 반환하십니다.
객관식 문제에서는 LLM이 제시한 최종 값이나 내용을 선택지와 대조하여 일치하는 선택지 번호를 반환합니다. 선택지 자체가 숫자여도 값 자체가 아닌 그 값에 해당하는 선택지 번호를 반환합니다.
주관식 문제에서는 LLM이 제시한 정수 답을 그대로 반환합니다.

### 출력 구조
당신은 다음 구조에 따라 결과물을 반환해야 합니다.
```
{
  answers: [
    {
      question_number: int,
      correct_answer: int,
      llm_answer: int
    }
  ]
}
```
"""

    def __init__(
        self,
        api_key: str,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """@description 검증기·OpenAI 호환 클라이언트 초기화"""
        if not OPENAI_AVAILABLE:
            raise ImportError("openai 패키지가 설치되지 않았습니다. 실행: pip install openai")

        self.api_key = api_key
        self.model_id = model_id or self.MODEL_ID
        self.reasoning_effort = reasoning_effort or self.REASONING_EFFORT
        self.system_prompt = system_prompt if system_prompt is not None else self.SYSTEM_PROMPT
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)

    def _truncate_response_for_verification(self, raw_response: str) -> str:
        """@description 검증 입력용 긴 응답 앞·뒤 보존"""
        if len(raw_response) <= self.RESPONSE_TRUNCATION_THRESHOLD:
            return raw_response

        return (
            raw_response[: self.RESPONSE_TRUNCATION_HEAD]
            + self.RESPONSE_TRUNCATION_SEPARATOR
            + raw_response[-self.RESPONSE_TRUNCATION_TAIL :]
        )

    @staticmethod
    def _fenced_ranges(lines: List[str]) -> List[tuple[int, int]]:
        """@description fenced 블록 줄 범위 추출"""
        ranges = []
        start = None
        for index, line in enumerate(lines):
            if not _FENCE_LINE_PATTERN.match(line):
                continue
            if start is None:
                start = index
            else:
                ranges.append((start, index))
                start = None
        return ranges

    @staticmethod
    def _is_table_row(line: str) -> bool:
        """@description Markdown 표 행 여부 판별"""
        stripped = line.strip()
        if "|" not in stripped:
            return False
        cells = stripped.strip("|").split("|")
        return len(cells) >= 2

    @staticmethod
    def _is_table_separator(line: str) -> bool:
        """@description Markdown 표 구분선 여부 판별"""
        if not AnswerVerifier._is_table_row(line):
            return False
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return len(cells) >= 2 and all(
            _TABLE_SEPARATOR_CELL_PATTERN.fullmatch(cell) for cell in cells
        )

    @staticmethod
    def _trim_blank_edges(lines: List[str]) -> str:
        """@description 선택지 문맥 양끝 빈 줄 제거"""
        start = 0
        end = len(lines)
        while start < end and not lines[start].strip():
            start += 1
        while end > start and not lines[end - 1].strip():
            end -= 1
        return "\n".join(lines[start:end])

    @staticmethod
    def _has_all_option_markers(text: str) -> bool:
        """@description 다섯 선택지 표식 포함 여부 판별"""
        return all(marker in text for marker in _OPTION_MARKERS)

    @classmethod
    def _standalone_choice_blocks(
        cls, lines: List[str], fenced_ranges: List[tuple[int, int]]
    ) -> List[str]:
        """@description fenced 밖 독립 선택지 블록 추출"""
        fenced_lines = {
            line_index
            for start, end in fenced_ranges
            for line_index in range(start, end + 1)
        }
        marker_lines = [
            (index, line.lstrip()[0])
            for index, line in enumerate(lines)
            if index not in fenced_lines and _OPTION_LINE_PATTERN.match(line)
        ]
        candidates = [
            (index, cls._trim_blank_edges([lines[index]]))
            for index, line in enumerate(lines)
            if index not in fenced_lines and _COMPACT_OPTION_LINE_PATTERN.fullmatch(line)
        ]
        for marker_index in range(len(marker_lines) - len(_OPTION_MARKERS) + 1):
            window = marker_lines[marker_index : marker_index + len(_OPTION_MARKERS)]
            if [marker for _, marker in window] != list(_OPTION_MARKERS):
                continue

            start = window[0][0]
            end = window[-1][0] + 1
            while end < len(lines):
                if not lines[end].strip() or _OPTION_LINE_PATTERN.match(lines[end]):
                    break
                end += 1
            candidates.append((start, cls._trim_blank_edges(lines[start:end])))
        return [block for _, block in sorted(candidates)]

    @classmethod
    def _markdown_choice_tables(cls, lines: List[str]) -> List[str]:
        """@description Markdown 선택지 표 블록 추출"""
        tables = []
        for separator_index, line in enumerate(lines):
            if separator_index == 0 or not cls._is_table_separator(line):
                continue
            header_index = separator_index - 1
            if not cls._is_table_row(lines[header_index]):
                continue
            end = separator_index + 1
            while end < len(lines) and cls._is_table_row(lines[end]):
                end += 1
            table_lines = lines[header_index:end]
            table_text = cls._trim_blank_edges(table_lines)
            if cls._has_all_option_markers(table_text):
                tables.append(table_text)
        return tables

    @classmethod
    def _fenced_choice_context(
        cls, lines: List[str], fenced_ranges: List[tuple[int, int]]
    ) -> str:
        """@description fenced 선택지·삽입 위치 문맥 추출"""
        for range_index, (start, end) in enumerate(fenced_ranges):
            block_text = cls._trim_blank_edges(lines[start : end + 1])
            if not all(
                pattern.search(block_text)
                for pattern in _INSERTION_SLOT_PATTERNS.values()
            ):
                continue

            context_start = start
            if range_index:
                previous_start, previous_end = fenced_ranges[range_index - 1]
                if all(not lines[index].strip() for index in range(previous_end + 1, start)):
                    context_start = previous_start
            return cls._trim_blank_edges(lines[context_start : end + 1])

        for start, end in fenced_ranges:
            block_text = cls._trim_blank_edges(lines[start : end + 1])
            if cls._has_all_option_markers(block_text):
                return block_text
        return ""

    @classmethod
    def _unfenced_insertion_context(
        cls, lines: List[str], fenced_ranges: List[tuple[int, int]]
    ) -> str:
        """@description fenced 밖 삽입 위치 문단과 주어진 문장 추출"""
        fenced_lines = {
            line_index
            for start, end in fenced_ranges
            for line_index in range(start, end + 1)
        }
        paragraphs = []
        index = 0
        while index < len(lines):
            if index in fenced_lines or not lines[index].strip():
                index += 1
                continue
            start = index
            while (
                index < len(lines)
                and index not in fenced_lines
                and lines[index].strip()
            ):
                index += 1
            end = index
            paragraph_text = cls._trim_blank_edges(lines[start:end])
            if all(
                pattern.search(paragraph_text)
                for pattern in _INSERTION_SLOT_PATTERNS.values()
            ):
                paragraphs.append((start, end))

        if not paragraphs:
            return ""

        start, end = paragraphs[-1]
        context_start = start
        previous_ranges = [
            fenced_range for fenced_range in fenced_ranges if fenced_range[1] < start
        ]
        if previous_ranges:
            previous_start, previous_end = previous_ranges[-1]
            if all(not lines[line_index].strip() for line_index in range(previous_end + 1, start)):
                context_start = previous_start
        return cls._trim_blank_edges(lines[context_start:end])

    @classmethod
    def _extract_choice_context(cls, question_text: str) -> str:
        """@description 문제 본문에서 선택지 문맥만 추출"""
        if not question_text:
            return ""
        normalized_text = question_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized_text.split("\n")
        fenced_ranges = cls._fenced_ranges(lines)

        standalone_blocks = cls._standalone_choice_blocks(lines, fenced_ranges)
        if standalone_blocks:
            return standalone_blocks[-1]

        table_blocks = cls._markdown_choice_tables(lines)
        if table_blocks:
            return table_blocks[-1]

        fenced_context = cls._fenced_choice_context(lines, fenced_ranges)
        if fenced_context:
            return fenced_context
        return cls._unfenced_insertion_context(lines, fenced_ranges)

    def verify_answer(
        self,
        raw_response: str,
        correct_answer: int,
        question_number: int,
        question_text: Optional[str] = None,
    ) -> Optional[int]:
        """@description LLM 응답 최종 답 추출"""
        truncated_response = self._truncate_response_for_verification(raw_response)

        if question_text:
            choice_context = self._extract_choice_context(question_text)
            user_message = f"""<choices>
{choice_context}
</choices>
<response>
{truncated_response}
</response>
<correct_answer>
The correct answer is {correct_answer}
</correct_answer>"""
        else:
            user_message = f"""<response>
{truncated_response}
</response>
<correct_answer>
The correct answer is {correct_answer}
</correct_answer>"""

        schema = {
            "type": "object",
            "properties": {
                "correct_answer": {"type": "integer", "description": "정답"},
                "llm_answer": {
                    "type": "integer",
                    "description": "LLM이 응답에서 추출한 답",
                },
            },
            "required": ["correct_answer", "llm_answer"],
            "additionalProperties": False,
        }

        try:
            response = self.client.responses.create(
                model=self.model_id,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": self.system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_message}],
                    },
                ],
                reasoning={"effort": self.reasoning_effort},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "answer_verification",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )
            result = json.loads(response.output_text)
            return result.get("llm_answer")

        except Exception as error:
            print(f"  ⚠ 추출 오류: {error}")
            return None

    def _build_hard_user_message(
        self, raw_response: str, question_infos: List[Dict[str, Any]]
    ) -> str:
        """@description hard 섹션 검증용 사용자 메시지 생성"""
        question_blocks = []
        for question_info in sorted(question_infos, key=lambda item: item["number"]):
            question_number = question_info["number"]
            question_text = question_info.get("question_text") or ""
            choice_context = self._extract_choice_context(question_text)
            correct_answer = question_info["correct_answer"]
            question_blocks.append(
                f"""<question_{question_number}>
<question_{question_number}_choices>
{choice_context}
</question_{question_number}_choices>
<correct_answer>
The correct answer is {correct_answer}
</correct_answer>
</question_{question_number}>"""
            )

        question_part = "\n\n".join(question_blocks)
        return f"""{question_part}

<response>
{raw_response}
</response>"""

    def verify_hard_answers(
        self, raw_response: str, question_infos: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, int]]]:
        """@description hard 섹션 응답 문항별 최종 답 추출"""
        user_message = self._build_hard_user_message(raw_response, question_infos)
        schema = {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_number": {"type": "integer", "description": "문항 번호"},
                            "correct_answer": {"type": "integer", "description": "정답"},
                            "llm_answer": {
                                "type": "integer",
                                "description": "LLM이 응답에서 추출한 답",
                            },
                        },
                        "required": ["question_number", "correct_answer", "llm_answer"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["answers"],
            "additionalProperties": False,
        }

        try:
            response = self.client.responses.create(
                model=self.model_id,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": self.HARD_SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_message}],
                    },
                ],
                reasoning={"effort": self.reasoning_effort},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "hard_answer_verification",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )
            result = json.loads(response.output_text)
            answers = result.get("answers")
            if not isinstance(answers, list):
                return None

            normalized_answers = []
            for answer in answers:
                normalized_answers.append(
                    {
                        "question_number": int(answer["question_number"]),
                        "correct_answer": int(answer["correct_answer"]),
                        "llm_answer": int(answer["llm_answer"]),
                    }
                )
            return normalized_answers

        except Exception as error:
            print(f"  ⚠ hard 추출 오류: {error}")
            return None


__all__ = ["AnswerVerifier", "OPENAI_AVAILABLE"]
