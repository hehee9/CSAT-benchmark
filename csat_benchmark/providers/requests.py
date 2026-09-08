"""@description 공급자별 요청 본문·멀티모달 콘텐츠 생성 공용 모듈"""

from __future__ import annotations

import base64
import copy
import mimetypes
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..models import ModelConfig, Question


_OPENAI_MAX_TOKENS_MODELS = {"gpt-4.1", "gpt-4o-2024-11-20"}
HARD_SECTION_PROMPT = "제시된 모든 문제를 해결하라."
_QUESTION_RANGE_PATTERN = re.compile(r"\[(\d+)\s*[～~\-]\s*(\d+)\]")
_FENCED_MATERIAL_PATTERN = re.compile(
    r"(?ms)^[ \t]*```[^\r\n]*\r?\n.*?^[ \t]*```[ \t]*(?:\r?$)"
)
_TABLE_ROW_PATTERN = re.compile(r"^\s*\|[^\r\n]*\|\s*$")
_TABLE_SEPARATOR_PATTERN = re.compile(
    r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$"
)
_GOOGLE_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


def format_hard_question_text(question_number: int, question_text: str) -> str:
    """@description hard 입력용 문항 텍스트 정규화(문항 번호 중복 제거)"""
    normalized_text = question_text.strip()
    if not normalized_text:
        return f"{question_number}."

    numbered_pattern = rf"^\s*{re.escape(str(question_number))}\s*(?:\.|번)"
    if re.match(numbered_pattern, normalized_text):
        return normalized_text
    return f"{question_number}. {normalized_text}"


def split_hard_question_text(question_number: int, question_text: str) -> tuple[str, str]:
    """@description 공통 지문·문항 고유 본문 분리"""
    normalized_text = question_text.strip()
    if not normalized_text:
        return "", f"{question_number}."

    question_start_pattern = rf"(?m)^\s*{re.escape(str(question_number))}\s*(?:\.|번)"
    match = re.search(question_start_pattern, normalized_text)
    if not match:
        return "", format_hard_question_text(question_number, normalized_text)
    return normalized_text[:match.start()].strip(), normalized_text[match.start():].strip()


def _normalize_shared_text(text: str) -> str:
    """@description 공통 본문 비교용 줄바꿈·행 끝 공백 정규화"""
    normalized_lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized = "\n".join(normalized_lines)
    normalized = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n\n", normalized)
    return normalized.strip()


def _extract_question_range(shared_text: str) -> tuple[int, int] | None:
    """@description 공통 본문 문항 범위 추출"""
    match = _QUESTION_RANGE_PATTERN.search(shared_text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _extract_fenced_material(text: str) -> tuple[int, int, str] | None:
    """@description 문항 본문 내 fenced 구조 자료 추출"""
    match = _FENCED_MATERIAL_PATTERN.search(text)
    if match is None:
        return None
    return match.start(), match.end(), match.group(0)


def _extract_table_material(text: str) -> tuple[int, int, str] | None:
    """@description 문항 본문 내 Markdown 표 자료 추출"""
    lines = text.splitlines(keepends=True)
    offsets: List[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    for start, line in enumerate(lines):
        if not _TABLE_ROW_PATTERN.match(line.rstrip("\r\n")):
            continue
        end = start
        while end < len(lines) and _TABLE_ROW_PATTERN.match(lines[end].rstrip("\r\n")):
            end += 1
        table_lines = lines[start:end]
        if len(table_lines) < 2 or not any(
            _TABLE_SEPARATOR_PATTERN.match(table_line.rstrip("\r\n"))
            for table_line in table_lines
        ):
            continue
        return offsets[start], offsets[end - 1] + len(lines[end - 1]), "".join(table_lines)
    return None


def _extract_structured_material(text: str) -> tuple[int, int, str, str] | None:
    """@description 문항 본문 내 구조 자료와 유형 추출"""
    candidates = []
    fenced = _extract_fenced_material(text)
    if fenced is not None:
        candidates.append((*fenced, "fenced"))
    table = _extract_table_material(text)
    if table is not None:
        candidates.append((*table, "table"))
    if not candidates:
        return None
    material = min(candidates, key=lambda candidate: candidate[0])
    if material[3] == "fenced":
        body_lines = material[2].splitlines()[1:-1]
        first_content_line = next((line.strip() for line in body_lines if line.strip()), "")
        if re.match(r"^(?:<보기>|보기|[①-⑤])", first_content_line):
            return None
    return material


def _remove_structured_material(text: str, material_range: tuple[int, int]) -> str:
    """@description 문항별 본문에서 공통 구조 자료 제거"""
    start, end = material_range
    prefix = text[:start].rstrip()
    suffix = text[end:].lstrip()
    if prefix and suffix:
        return f"{prefix}\n\n{suffix}"
    return prefix or suffix


def format_image_caption(image_paths: Iterable[str | Path], *, merged: bool = False) -> str:
    """@description 이미지 파일명 기반 요청 본문 식별자 생성"""
    stems = [Path(path).stem for path in image_paths]
    if not merged:
        if len(stems) != 1:
            raise ValueError("병합하지 않는 이미지 캡션은 파일명 하나가 필요합니다.")
        return f"[이미지:{stems[0]}]"
    ordered = ", ".join(
        f"{stem} (위에서부터 {index})" for index, stem in enumerate(stems, start=1)
    )
    return f"[이미지:{ordered}]"


def _shared_material_label(
    questions: List[Any],
    shared_text: str,
) -> str:
    """@description 공통 구조 자료 식별 문구 생성"""
    question_range = _extract_question_range(shared_text)
    if question_range is not None:
        return f"공통 자료 [{question_range[0]}～{question_range[1]}]"
    first_number = questions[0].number
    last_number = questions[-1].number
    if first_number == last_number:
        return f"공통 자료 (문항 {first_number})"
    return f"공통 자료 (문항 {first_number}～{last_number})"


def _deduplicate_structured_material(
    questions: List[Any],
    item_texts: List[str],
    shared_text: str,
) -> List[str]:
    """@description 인접 문항의 동일 구조 자료 단일 블록 이동"""
    result: List[str] = []
    index = 0
    while index < len(questions):
        material = _extract_structured_material(item_texts[index])
        if material is None:
            result.append(item_texts[index])
            index += 1
            continue

        material_start, material_end, material_text, material_type = material
        material_key = _normalize_shared_text(material_text)
        group_end = index + 1
        question_range = _extract_question_range(shared_text)
        while group_end < len(questions):
            next_question = questions[group_end]
            previous_question = questions[group_end - 1]
            if next_question.number != previous_question.number + 1:
                break
            if question_range is not None and not question_range[0] <= next_question.number <= question_range[1]:
                break
            next_material = _extract_structured_material(item_texts[group_end])
            if next_material is None or next_material[3] != material_type:
                break
            if _normalize_shared_text(next_material[2]) != material_key:
                break
            group_end += 1

        if group_end - index == 1:
            result.append(item_texts[index])
            index += 1
            continue

        grouped_questions = questions[index:group_end]
        result.append(
            f"{_shared_material_label(grouped_questions, shared_text)}\n\n{material_text.rstrip()}"
        )
        for grouped_index in range(index, group_end):
            grouped_material = _extract_structured_material(item_texts[grouped_index])
            assert grouped_material is not None
            result.append(
                _remove_structured_material(
                    item_texts[grouped_index],
                    (grouped_material[0], grouped_material[1]),
                )
            )
        index = group_end
    return result


def build_hard_section_text_blocks(questions: List[Any]) -> List[str]:
    """@description hard 입력 블록 생성(공통 지문·구조 자료 중복 제거)"""
    sorted_questions = sorted(questions, key=lambda item: item.number)
    blocks = [HARD_SECTION_PROMPT]
    index = 0
    while index < len(sorted_questions):
        question = sorted_questions[index]
        shared_text, item_text = split_hard_question_text(
            question.number,
            question.load_question_text(),
        )
        group_questions = [question]
        group_item_texts = [item_text]
        normalized_shared_text = _normalize_shared_text(shared_text)
        group_end = index + 1
        while group_end < len(sorted_questions):
            next_question = sorted_questions[group_end]
            next_shared_text, next_item_text = split_hard_question_text(
                next_question.number,
                next_question.load_question_text(),
            )
            if _normalize_shared_text(next_shared_text) != normalized_shared_text:
                break
            group_questions.append(next_question)
            group_item_texts.append(next_item_text)
            group_end += 1

        if shared_text:
            blocks.append(shared_text)
        blocks.extend(
            _deduplicate_structured_material(
                group_questions,
                group_item_texts,
                shared_text,
            )
        )
        index = group_end
    return blocks


def get_mime_type(file_path: str | Path) -> str:
    """
    @description 파일 확장자 기반 공급자 요청용 MIME 타입 확인

    @param file_path 파일 경로
    @return MIME 타입 문자열
    """
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "image/png"


def encode_image(image_path: str | Path) -> tuple[str, str]:
    """
    @description 이미지 파일 Base64 문자열 인코딩

    @param image_path 이미지 파일 경로
    @return (MIME 타입, Base64 문자열)
    """
    path = Path(image_path)
    with path.open("rb") as image_file:
        return get_mime_type(path), base64.b64encode(image_file.read()).decode("ascii")


def _existing_paths(paths: Iterable[str], *, skip_missing: bool) -> List[Path]:
    resolved = [Path(path) for path in paths]
    if skip_missing:
        return [path for path in resolved if path.exists()]
    return resolved


def _merge_images(image_paths: List[Path]) -> Optional[Dict[str, Any]]:
    """@description 복수 이미지 단일 PNG 병합"""
    from PIL import Image

    opened_images = []
    try:
        for image_path in image_paths:
            with Image.open(image_path) as image:
                opened_images.append(image.convert("RGBA"))

        if len(opened_images) < 2:
            return None

        gap_px = 40
        max_width = max(image.width for image in opened_images)
        total_height = sum(image.height for image in opened_images)
        total_height += gap_px * (len(opened_images) - 1)
        composite = Image.new("RGBA", (max_width, total_height), (255, 255, 255, 255))
        current_y = 0
        for image in opened_images:
            x_offset = (max_width - image.width) // 2
            composite.alpha_composite(image, (x_offset, current_y))
            current_y += image.height + gap_px

        output = BytesIO()
        composite.convert("RGB").save(output, format="PNG")
        return {
            "mime_type": "image/png",
            "image_data": base64.b64encode(output.getvalue()).decode("ascii"),
        }
    finally:
        for image in opened_images:
            image.close()


def _resize_anthropic_image_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """@description Anthropic 복수 이미지 요청용 최대 크기 제한 적용"""
    from PIL import Image

    image_bytes = base64.b64decode(payload["image_data"])
    with Image.open(BytesIO(image_bytes)) as image:
        if max(image.size) <= 2000:
            return payload

        image_format = image.format
        image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        resized_bytes = BytesIO()
        image.save(resized_bytes, format=image_format)

    resized_payload = payload.copy()
    resized_payload["image_data"] = base64.b64encode(
        resized_bytes.getvalue()
    ).decode("ascii")
    return resized_payload


def _image_payloads(
    question: Any,
    *,
    supports_vision: bool,
    merge_multiple_images: bool,
    skip_missing: bool,
) -> List[Dict[str, Any]]:
    if not supports_vision:
        return []

    image_paths = _existing_paths(question.image_paths, skip_missing=skip_missing)
    if merge_multiple_images and len(image_paths) >= 2:
        merged = _merge_images(image_paths)
        if merged is not None:
            merged["filenames"] = [str(path) for path in image_paths]
            return [merged]

    return [
        {
            "mime_type": mime_type,
            "image_data": encoded_image,
            "filename": str(path),
        }
        for path, (mime_type, encoded_image) in (
            (path, encode_image(path)) for path in image_paths
        )
    ]


def _section_image_caption(question: Any, payload: Dict[str, Any]) -> str | None:
    """@description synthetic section 이미지 payload 식별 문구 생성"""
    if question.number != 0:
        return None
    filenames = payload.get("filenames")
    if filenames is not None:
        return format_image_caption(filenames, merged=True)
    return format_image_caption([payload["filename"]])


def _pdf_payloads(question: Question, *, skip_missing: bool) -> List[Dict[str, str]]:
    """@description PDF 파일 Base64 전송 데이터 생성"""
    payloads: List[Dict[str, str]] = []
    for pdf_path in _existing_paths(question.pdf_paths, skip_missing=skip_missing):
        with pdf_path.open("rb") as pdf_file:
            payloads.append(
                {
                    "filename": pdf_path.name,
                    "data": base64.b64encode(pdf_file.read()).decode("ascii"),
                }
            )
    return payloads


def validate_question_media(
    question: Question,
    config: ModelConfig,
    *,
    batch: bool = False,
) -> None:
    """@description 공급자·배치 매체 지원 범위 검증"""
    if question.image_paths and not config.supports_vision:
        raise ValueError(f"{config.name} 모델은 이미지 매체를 지원하지 않습니다.")

    if question.pdf_paths:
        if batch:
            raise ValueError("배치 요청은 PDF 매체를 지원하지 않습니다.")
        if config.api_type == "deepseek" or not config.supports_vision:
            raise ValueError(f"{config.name} 모델은 PDF 매체를 지원하지 않습니다.")

    if question.audio_paths:
        if batch:
            raise ValueError("배치 요청은 오디오 매체를 지원하지 않습니다.")
        if config.api_type != "google":
            raise ValueError(f"{config.name} 모델은 오디오 매체를 지원하지 않습니다.")

    if question.video_paths:
        if batch:
            raise ValueError("배치 요청은 동영상 매체를 지원하지 않습니다.")
        if config.api_type != "google":
            raise ValueError(f"{config.name} 모델은 동영상 매체를 지원하지 않습니다.")


def build_chat_content(
    question: Any,
    *,
    supports_vision: bool = True,
    image_url_mode: str = "data_url",
    merge_multiple_images: bool = False,
    skip_missing: bool = True,
) -> List[Dict[str, Any]]:
    """
    @description OpenAI 호환 Chat Completions 사용자 content 구성

    @param question 문제 객체
    @param supports_vision 이미지 전송 허용 여부
    @param image_url_mode data_url 또는 raw_base64 형식
    @param merge_multiple_images 복수 이미지 병합 여부
    @param skip_missing 누락 이미지 건너뛰기 여부
    @return Chat Completions content 목록
    """
    content: List[Dict[str, Any]] = []
    for payload in _pdf_payloads(question, skip_missing=skip_missing):
        content.append(
            {
                "type": "file",
                "file": {
                    "filename": payload["filename"],
                    "file_data": f"data:application/pdf;base64,{payload['data']}",
                },
            }
        )

    for payload in _image_payloads(
        question,
        supports_vision=supports_vision,
        merge_multiple_images=merge_multiple_images,
        skip_missing=skip_missing,
    ):
        image_caption = _section_image_caption(question, payload)
        if image_caption is not None:
            content.append({"type": "text", "text": image_caption})
        image_url = payload["image_data"]
        if image_url_mode != "raw_base64":
            image_url = f"data:{payload['mime_type']};base64,{image_url}"
        content.append({"type": "image_url", "image_url": {"url": image_url}})

    question_text = question.load_question_text()
    if question_text:
        content.append({"type": "text", "text": question_text})
    return content


def build_responses_content(
    question: Any,
    *,
    supports_vision: bool = True,
    image_format: str = "data_url",
    skip_missing: bool = True,
) -> List[Dict[str, Any]]:
    """
    @description OpenAI Responses API 사용자 content 구성

    @param question 문제 객체
    @param supports_vision 이미지 전송 허용 여부
    @param image_format data_url 또는 base64_source 형식
    @param skip_missing 누락 이미지 건너뛰기 여부
    @return Responses API content 목록
    """
    content: List[Dict[str, Any]] = []
    for payload in _pdf_payloads(question, skip_missing=skip_missing):
        content.append(
            {
                "type": "input_file",
                "filename": payload["filename"],
                "file_data": f"data:application/pdf;base64,{payload['data']}",
            }
        )

    for payload in _image_payloads(
        question,
        supports_vision=supports_vision,
        merge_multiple_images=False,
        skip_missing=skip_missing,
    ):
        image_caption = _section_image_caption(question, payload)
        if image_caption is not None:
            content.append({"type": "input_text", "text": image_caption})
        if image_format == "base64_source":
            content.append(
                {
                    "type": "input_image",
                    "source": {
                        "type": "base64",
                        "media_type": payload["mime_type"],
                        "data": payload["image_data"],
                    },
                }
            )
        else:
            content.append(
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{payload['mime_type']};base64,{payload['image_data']}"
                    ),
                }
            )

    question_text = question.load_question_text()
    if question_text:
        content.append({"type": "input_text", "text": question_text})
    return content


def build_anthropic_content(
    question: Any,
    *,
    supports_vision: bool = True,
    skip_missing: bool = True,
) -> List[Dict[str, Any]]:
    """@description Anthropic Messages API 사용자 content 구성"""
    content: List[Dict[str, Any]] = []
    for payload in _pdf_payloads(question, skip_missing=skip_missing):
        content.append(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": payload["data"],
                },
            }
        )

    image_payloads = _image_payloads(
        question,
        supports_vision=supports_vision,
        merge_multiple_images=False,
        skip_missing=skip_missing,
    )
    if len(image_payloads) > 20:
        image_payloads = [
            _resize_anthropic_image_payload(payload) for payload in image_payloads
        ]

    for payload in image_payloads:
        image_caption = _section_image_caption(question, payload)
        if image_caption is not None:
            content.append({"type": "text", "text": image_caption})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": payload["mime_type"],
                    "data": payload["image_data"],
                },
            }
        )

    question_text = question.load_question_text() or f"문제 {question.number}번"
    content.append({"type": "text", "text": question_text})
    return content


def build_google_parts(
    question: Any,
    *,
    supports_vision: bool = True,
    wire_format: str = "camel",
    skip_missing: bool = False,
) -> List[Dict[str, Any]]:
    """
    @description Gemini GenerateContent parts 구성

    @param question 문제 객체
    @param supports_vision 이미지 전송 허용 여부
    @param wire_format camel 또는 snake REST 필드명
    @param skip_missing 누락 이미지 건너뛰기 여부
    @return Gemini parts 목록
    """
    parts: List[Dict[str, Any]] = []
    question_text = question.load_question_text()
    if question_text:
        parts.append({"text": question_text})

    image_payloads = _image_payloads(
        question,
        supports_vision=supports_vision,
        merge_multiple_images=False,
        skip_missing=skip_missing,
    )
    if wire_format == "snake":
        for payload in image_payloads:
            image_caption = _section_image_caption(question, payload)
            if image_caption is not None:
                parts.append({"text": image_caption})
            parts.append(
                {
                    "inline_data": {
                        "mime_type": payload["mime_type"],
                        "data": payload["image_data"],
                    }
                }
            )
    else:
        for payload in image_payloads:
            image_caption = _section_image_caption(question, payload)
            if image_caption is not None:
                parts.append({"text": image_caption})
            parts.append(
                {
                    "inlineData": {
                        "mimeType": payload["mime_type"],
                        "data": payload["image_data"],
                    }
                }
            )
    return parts


def build_anthropic_thinking_config(config: Any) -> Dict[str, Any]:
    """@description Anthropic Messages·Message Batches 공통 추론 설정 생성"""
    thinking_config: Dict[str, Any] = {}
    if config.thinking_enabled and config.thinking_budget_tokens:
        thinking_config["thinking"] = {
            "type": "enabled",
            "budget_tokens": config.thinking_budget_tokens,
        }
    elif config.thinking_enabled:
        thinking_config["thinking"] = {"type": "adaptive"}
    elif _supports_anthropic_thinking_disabled(config.model_id):
        thinking_config["thinking"] = {"type": "disabled"}

    if config.reasoning_effort:
        thinking_config["output_config"] = {"effort": config.reasoning_effort}
    return thinking_config


def _supports_anthropic_thinking_disabled(model_id: str) -> bool:
    import re

    match = re.match(r"^claude-(opus|sonnet)-(\d+)(?:-|$)", model_id)
    return bool(match and int(match.group(2)) >= 5)


def build_google_generation_config(config: Any) -> Dict[str, Any]:
    """@description Gemini 배치 요청 generationConfig 생성"""
    generation_config: Dict[str, Any] = {"maxOutputTokens": config.max_tokens}
    if config.thinking_level:
        generation_config["thinkingConfig"] = {"thinkingLevel": config.thinking_level}
    elif config.thinking_budget is not None:
        generation_config["thinkingConfig"] = {"thinkingBudget": config.thinking_budget}
    return generation_config


def build_google_request(
    question: Any,
    config: Any,
    *,
    system_prompt: Optional[str] = None,
    supports_vision: Optional[bool] = None,
) -> Dict[str, Any]:
    """@description Gemini 배치용 GenerateContent 요청 본문 생성"""
    request: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": build_google_parts(
                    question,
                    supports_vision=(
                        config.supports_vision
                        if supports_vision is None
                        else supports_vision
                    ),
                ),
            }
        ],
        "generationConfig": build_google_generation_config(config),
        "safetySettings": copy.deepcopy(_GOOGLE_SAFETY_SETTINGS),
    }
    if system_prompt:
        request["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    return request


def build_chat_options(
    config: Any,
    *,
    stream: bool = False,
    include_stream_usage: bool = False,
    openrouter_reasoning: bool = False,
    extra_body_mode: str = "nested",
) -> Dict[str, Any]:
    """@description OpenAI 호환 Chat Completions 전송 옵션 구성"""
    body: Dict[str, Any] = {"model": config.model_id}
    if config.model_id in _OPENAI_MAX_TOKENS_MODELS or config.api_type in {"vllm"}:
        body["max_tokens"] = config.max_tokens
    else:
        body["max_completion_tokens"] = config.max_tokens
    if stream:
        body["stream"] = True
        if include_stream_usage:
            body["stream_options"] = {"include_usage": True}
    if config.reasoning_effort:
        if openrouter_reasoning and "openrouter.ai" in (config.base_url or "").lower():
            body.setdefault("extra_body", {}).setdefault("reasoning", {})["effort"] = (
                config.reasoning_effort
            )
        else:
            body["reasoning_effort"] = config.reasoning_effort
    if config.modalities:
        body["modalities"] = config.modalities
    if config.api_type == "friendli" and config.friendli_thinking:
        body.setdefault("extra_body", {}).update(
            {
                "parse_reasoning": True,
                "chat_template_kwargs": {"enable_thinking": True},
            }
        )
    if config.extra_body:
        if extra_body_mode == "top_level":
            body.update(copy.deepcopy(config.extra_body))
        else:
            body.setdefault("extra_body", {}).update(copy.deepcopy(config.extra_body))
    return body


def build_chat_body(
    question: Any,
    config: Any,
    *,
    system_prompt: Optional[str] = None,
    stream: bool = False,
    include_stream_usage: bool = False,
    skip_missing: bool = True,
    supports_vision: Optional[bool] = None,
    image_url_mode: Optional[str] = None,
    merge_multiple_images: Optional[bool] = None,
    openrouter_reasoning: bool = False,
    extra_body_mode: str = "nested",
) -> Dict[str, Any]:
    """@description OpenAI 호환 Chat Completions 요청 본문 생성"""
    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {
            "role": "user",
            "content": build_chat_content(
                question,
                supports_vision=(
                    config.supports_vision
                    if supports_vision is None
                    else supports_vision
                ),
                image_url_mode=(
                    config.image_url_mode if image_url_mode is None else image_url_mode
                ),
                merge_multiple_images=(
                    config.merge_multiple_images
                    if merge_multiple_images is None
                    else merge_multiple_images
                ),
                skip_missing=skip_missing,
            ),
        }
    )

    body = build_chat_options(
        config,
        stream=stream,
        include_stream_usage=include_stream_usage,
        openrouter_reasoning=openrouter_reasoning,
        extra_body_mode=extra_body_mode,
    )
    body["messages"] = messages
    return body


def build_responses_body(
    question: Any,
    config: Any,
    *,
    system_prompt: Optional[str] = None,
    stream: bool = False,
    image_format: str = "data_url",
    skip_missing: bool = True,
    supports_vision: Optional[bool] = None,
    reasoning_format: str = "legacy",
    extra_body_mode: str = "nested",
    include_extra_body: bool = True,
) -> Dict[str, Any]:
    """@description OpenAI Responses API 요청 본문 생성"""
    body: Dict[str, Any] = {
        "model": config.model_id,
        "input": [
            {
                "role": "user",
                "content": build_responses_content(
                    question,
                    supports_vision=(
                        config.supports_vision
                        if supports_vision is None
                        else supports_vision
                    ),
                    image_format=image_format,
                    skip_missing=skip_missing,
                ),
            }
        ],
    }
    if system_prompt:
        body["instructions"] = system_prompt
    if stream:
        body["stream"] = True
    if reasoning_format == "legacy":
        if config.reasoning_effort:
            body["reasoning_effort"] = config.reasoning_effort
    else:
        reasoning: Dict[str, str] = {}
        if config.reasoning_effort:
            reasoning["effort"] = config.reasoning_effort
        if config.reasoning_mode:
            reasoning["mode"] = config.reasoning_mode
        if reasoning:
            body["reasoning"] = reasoning
    if include_extra_body and config.extra_body:
        if extra_body_mode == "top_level":
            body.update(copy.deepcopy(config.extra_body))
        else:
            body.setdefault("extra_body", {}).update(copy.deepcopy(config.extra_body))
    return body


def build_anthropic_params(
    question: Any,
    config: Any,
    *,
    system_prompt: Optional[str] = None,
    skip_missing: bool = True,
    supports_vision: Optional[bool] = None,
) -> Dict[str, Any]:
    """@description Anthropic Messages API·Message Batches 공통 파라미터 생성"""
    params: Dict[str, Any] = {
        "model": config.model_id,
        "max_tokens": config.max_tokens,
        "messages": [
            {
                "role": "user",
                "content": build_anthropic_content(
                    question,
                    supports_vision=(
                        config.supports_vision
                        if supports_vision is None
                        else supports_vision
                    ),
                    skip_missing=skip_missing,
                ),
            }
        ],
    }
    if system_prompt:
        params["system"] = system_prompt
    params.update(build_anthropic_thinking_config(config))
    return params
