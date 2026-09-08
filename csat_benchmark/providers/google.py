"""@description Google Gemini 공급자 클라이언트"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Dict

import requests

from ..models import APIResponse, ModelConfig, Question
from .base import APIClient
from .requests import build_google_parts, format_image_caption

genai = None
types = None
genai_old = None
GOOGLE_GENAI_AVAILABLE = False
GOOGLE_GENERATIVEAI_AVAILABLE = False
PILImage = None
PIL_AVAILABLE = False

def _ensure_google_available() -> bool:
    """@description Gemini 요청 시 Google SDK 지연 로드"""
    global genai, types, genai_old, GOOGLE_GENAI_AVAILABLE, GOOGLE_GENERATIVEAI_AVAILABLE
    if GOOGLE_GENAI_AVAILABLE or GOOGLE_GENERATIVEAI_AVAILABLE:
        return True
    try:
        from google import genai as genai_module
        from google.genai import types as genai_types
    except (ImportError, AttributeError):
        GOOGLE_GENAI_AVAILABLE = False
        try:
            import google.generativeai as legacy_genai
        except ImportError:
            GOOGLE_GENERATIVEAI_AVAILABLE = False
            return False
        genai_old = legacy_genai
        GOOGLE_GENERATIVEAI_AVAILABLE = True
        return True
    genai = genai_module
    types = genai_types
    GOOGLE_GENAI_AVAILABLE = True
    return True


def _ensure_pil_available() -> bool:
    """@description Gemini 이미지 첨부 시 PIL 지연 로드"""
    global PILImage, PIL_AVAILABLE
    if PIL_AVAILABLE:
        return True
    try:
        from PIL import Image as ImageClass
    except ImportError:
        PIL_AVAILABLE = False
        return False
    PILImage = ImageClass
    PIL_AVAILABLE = True
    return True

class GoogleClient(APIClient):
    """@description Google Gemini API 클라이언트"""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        if not _ensure_google_available():
            raise ImportError("Google AI 패키지가 설치되지 않았습니다. 실행: pip install google-generativeai")

        # Vertex AI Express 모드 판별(vertex_key 우선)
        self.use_vertex = bool(config.vertex_key)

        if self.use_vertex:
            # Vertex AI Express: vertex_key 사용
            self._current_key = config.vertex_key
            if GOOGLE_GENAI_AVAILABLE:
                self.client = genai.Client(vertexai=True, api_key=config.vertex_key)
                self.use_new_sdk = True
            else:
                # 레거시 SDK: Vertex AI Express 미지원 → AI Studio 폴백
                print(f"경고: '{config.name}' - Legacy SDK에서 Vertex AI Express 미지원, AI Studio로 폴백")
                self.use_vertex = False
                self._current_key = self._api_keys[0]
                genai_old.configure(api_key=self._current_key)
                self.client = genai_old.GenerativeModel(config.model_id)
                self.use_new_sdk = False
        else:
            # AI Studio 방식
            self._current_key = self._api_keys[0]
            if GOOGLE_GENAI_AVAILABLE:
                self.client = genai.Client(api_key=self._current_key)
                self.use_new_sdk = True
            else:
                genai_old.configure(api_key=self._current_key)
                self.client = genai_old.GenerativeModel(config.model_id)
                self.use_new_sdk = False

        self.model_id = config.model_id
        self._uploaded_files = {}  # 파일 경로 → file_uri 매핑 캐시

    def _get_mime_type(self, file_path: Path) -> str:
        """@description 파일 확장자 기반 MIME 타입 결정"""
        ext = file_path.suffix.lower()
        mime_types = {
            # 이미지 MIME 타입
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            # PDF MIME 타입
            '.pdf': 'application/pdf',
            # 오디오 MIME 타입
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.aiff': 'audio/aiff',
            '.aac': 'audio/aac',
            '.ogg': 'audio/ogg',
            '.flac': 'audio/flac',
            # 동영상 MIME 타입
            '.mp4': 'video/mp4',
            '.mpeg': 'video/mpeg',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.wmv': 'video/x-ms-wmv',
            '.mpg': 'video/mpeg',
            '.webm': 'video/webm',
            '.flv': 'video/x-flv',
        }
        return mime_types.get(ext, 'application/octet-stream')

    def _upload_file_rest(self, file_path: Path) -> str:
        """
        @description REST API 기반 파일 업로드(curl 방식)
        @return 업로드 파일 URI
        """
        # 캐시 파일 재사용
        path_str = str(file_path)
        if path_str in self._uploaded_files:
            return self._uploaded_files[path_str]

        base_url = "https://generativelanguage.googleapis.com"
        mime_type = self._get_mime_type(file_path)
        file_size = file_path.stat().st_size
        display_name = file_path.name

        # 1단계: Resumable upload 시작
        start_url = f"{base_url}/upload/v1beta/files?key={self._current_key}"
        start_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json"
        }
        start_data = {"file": {"display_name": display_name}}

        start_response = requests.post(start_url, headers=start_headers, json=start_data)
        if start_response.status_code != 200:
            raise Exception(f"File upload start failed: {start_response.status_code} - {start_response.text}")

        # 업로드 URL 추출
        upload_url = start_response.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise Exception("Upload URL not found in response headers")

        # 2단계: 파일 데이터 업로드
        with open(file_path, 'rb') as f:
            file_data = f.read()

        upload_headers = {
            "X-Goog-Upload-Command": "upload, finalize",
            "Content-Length": str(file_size)
        }

        upload_response = requests.post(upload_url, headers=upload_headers, data=file_data)
        if upload_response.status_code != 200:
            raise Exception(f"File upload failed: {upload_response.status_code} - {upload_response.text}")

        result = upload_response.json()
        file_uri = result.get("file", {}).get("uri")
        if not file_uri:
            raise Exception(f"File URI not found in response: {result}")

        # 업로드 URI 캐시 저장
        self._uploaded_files[path_str] = file_uri
        return file_uri

    def _upload_file_sdk(self, file_path: Path) -> str:
        """
        @description SDK 기반 파일 업로드
        @return 업로드 파일 URI
        """
        # 캐시 파일 재사용
        path_str = str(file_path)
        if path_str in self._uploaded_files:
            return self._uploaded_files[path_str]

        if self.use_new_sdk:
            # google-genai SDK
            uploaded_file = self.client.files.upload(file=file_path)
            file_uri = uploaded_file.uri
        else:
            # google-generativeai 레거시 SDK
            uploaded_file = genai_old.upload_file(file_path)
            file_uri = uploaded_file.uri

        # 업로드 URI 캐시 저장
        self._uploaded_files[path_str] = file_uri
        return file_uri

    def _wait_for_file_active(self, file_uri: str, timeout: int = 300) -> bool:
        """
        @description 동영상 파일 처리 완료 대기 및 상태 확인
        @param file_uri 업로드 파일 URI
        """
        # file_uri 형식: "https://generativelanguage.googleapis.com/v1beta/files/..."
        # 대체 형식: "files/..."
        if "files/" in file_uri:
            file_name = file_uri.split("files/")[-1]
        else:
            return True  # 미인식 URI 대기 생략

        check_url = f"https://generativelanguage.googleapis.com/v1beta/files/{file_name}?key={self._current_key}"

        start_time = time.time()
        while time.time() - start_time < timeout:
            response = requests.get(check_url)
            if response.status_code == 200:
                data = response.json()
                state = data.get("state", "ACTIVE")
                if state == "ACTIVE":
                    return True
                elif state == "FAILED":
                    raise Exception(f"File processing failed: {data}")
                # PROCESSING 상태 지속 시 대기
            time.sleep(2)

        raise Exception(f"File processing timeout after {timeout} seconds")

    def _request_and_collect(self, question: Question) -> tuple[str, Any]:
        """@description Google SDK 요청 실행 및 스트림 텍스트·사용량 수집"""
        question_text = question.load_question_text()
        if self.use_new_sdk:
            # google-genai SDK 사용
            content = [question_text]

            # 이미지 첨부(복수 이미지, PIL Image 직접 전달)
            if _ensure_pil_available():
                for image_path_str in question.image_paths:
                    image_path = Path(image_path_str)
                    if image_path.exists():
                        if question.number == 0:
                            content.append(format_image_caption([image_path]))
                        img = PILImage.open(image_path)
                        content.append(img)

            # PDF 파일 첨부(SDK 업로드)
            for pdf_path_str in question.pdf_paths:
                pdf_path = Path(pdf_path_str)
                if pdf_path.exists():
                    file_uri = self._upload_file_sdk(pdf_path)
                    mime_type = self._get_mime_type(pdf_path)
                    content.append(types.Part.from_uri(file_uri=file_uri, mime_type=mime_type))

            # 오디오 파일 첨부(SDK 업로드)
            for audio_path_str in question.audio_paths:
                audio_path = Path(audio_path_str)
                if audio_path.exists():
                    file_uri = self._upload_file_sdk(audio_path)
                    mime_type = self._get_mime_type(audio_path)
                    content.append(types.Part.from_uri(file_uri=file_uri, mime_type=mime_type))

            # 동영상 파일 첨부(SDK 업로드 및 처리 완료 대기)
            for video_path_str in question.video_paths:
                video_path = Path(video_path_str)
                if video_path.exists():
                    file_uri = self._upload_file_sdk(video_path)
                    self._wait_for_file_active(file_uri)
                    mime_type = self._get_mime_type(video_path)
                    content.append(types.Part.from_uri(file_uri=file_uri, mime_type=mime_type))

            # API 파라미터 구성
            gen_config_kwargs: Dict[str, Any] = {}
            if self.system_prompt:
                gen_config_kwargs["system_instruction"] = self.system_prompt

            # thinking_budget 설정(Gemini 추론)
            if self.config.thinking_budget is not None:
                gen_config_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=self.config.thinking_budget
                )
            gen_config = (
                types.GenerateContentConfig(**gen_config_kwargs)
                if gen_config_kwargs
                else None
            )

            # 스트리밍 응답 수집
            response_texts = []
            usage_metadata = None
            stream = self.client.models.generate_content_stream(
                model=self.model_id,
                contents=content,
                config=gen_config
            )
            for chunk in stream:
                if hasattr(chunk, 'text') and chunk.text:
                    response_texts.append(chunk.text)
            # 마지막 청크 usage_metadata 추출
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    usage_metadata = chunk.usage_metadata

            raw_response = "".join(response_texts)

        else:
            # google-generativeai 레거시 SDK 사용
            content = [question_text]

            # 이미지 첨부(복수 이미지 지원)
            if _ensure_pil_available():
                for image_path_str in question.image_paths:
                    image_path = Path(image_path_str)
                    if image_path.exists():
                        if question.number == 0:
                            content.append(format_image_caption([image_path]))
                        img = PILImage.open(image_path)
                        content.append(img)

            # PDF·오디오·동영상 파일 첨부(레거시 SDK 업로드)
            for pdf_path_str in question.pdf_paths:
                pdf_path = Path(pdf_path_str)
                if pdf_path.exists():
                    uploaded_file = genai_old.upload_file(pdf_path)
                    content.append(uploaded_file)

            for audio_path_str in question.audio_paths:
                audio_path = Path(audio_path_str)
                if audio_path.exists():
                    uploaded_file = genai_old.upload_file(audio_path)
                    content.append(uploaded_file)

            for video_path_str in question.video_paths:
                video_path = Path(video_path_str)
                if video_path.exists():
                    uploaded_file = genai_old.upload_file(video_path)
                    # 동영상 처리 완료 대기
                    while uploaded_file.state.name == "PROCESSING":
                        time.sleep(2)
                        uploaded_file = genai_old.get_file(uploaded_file.name)
                    content.append(uploaded_file)

            # generation_config 구성
            gen_config = {}
            if self.config.thinking_budget is not None:
                gen_config["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=self.config.thinking_budget,
                )

            # google-generativeai GenerativeModel 초기화 시 시스템 지침 전달
            legacy_client = self.client
            if self.system_prompt:
                legacy_client = genai_old.GenerativeModel(
                    self.model_id,
                    system_instruction=self.system_prompt,
                )

            # 스트리밍 응답 수집
            response_texts = []
            usage_metadata = None
            stream = legacy_client.generate_content(
                content,
                generation_config=gen_config if gen_config else None,
                stream=True  # 스트리밍 활성화
            )
            for chunk in stream:
                if hasattr(chunk, 'text') and chunk.text:
                    response_texts.append(chunk.text)
            # 마지막 청크 usage_metadata 추출
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    usage_metadata = chunk.usage_metadata

            raw_response = "".join(response_texts)

        return raw_response, usage_metadata

    def send_request(self, question: Question) -> APIResponse:
        """@description Google Gemini API 스트리밍 요청 전송"""
        # 요청별 API 키 로테이션(Vertex AI 모드 제외)
        if not self.use_vertex:
            next_key = self._get_next_api_key()
            if next_key != self._current_key:
                self._current_key = next_key
                if self.use_new_sdk:
                    self.client = genai.Client(api_key=self._current_key)
                else:
                    genai_old.configure(api_key=self._current_key)

        try:
            if self.config.thinking_level:
                return self._send_rest_api_request(question)

            raw_response, usage_metadata = self._request_and_collect(question)

            # answer = self._extract_answer(raw_response, question.choices)

            # Gemini usage_metadata 기반 토큰 사용량 추출
            input_tokens = None
            output_tokens = None
            total_tokens = None
            if usage_metadata:
                input_tokens = getattr(usage_metadata, 'prompt_token_count', None)
                output_tokens = getattr(usage_metadata, 'candidates_token_count', None)
                thoughts_tokens = getattr(usage_metadata, 'thoughts_token_count', None)
                total_tokens = getattr(usage_metadata, 'total_token_count', None)
        # 추론 토큰 → 출력 토큰 합산
                if thoughts_tokens and output_tokens:
                    output_tokens = output_tokens + thoughts_tokens

            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response=raw_response,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens
            )

        except Exception as e:
            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response="",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=False,
                error_message=str(e)
            )

    def _send_rest_api_request(self, question: Question) -> APIResponse:
        """@description Gemini REST API 스트리밍 요청 처리"""
        # 스트리밍 엔드포인트 사용(alt=sse 필수)
        if self.use_vertex:
            # Vertex AI Express REST 엔드포인트
            url = f"https://aiplatform.googleapis.com/v1beta1/publishers/google/models/{self.model_id}:streamGenerateContent?alt=sse"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self._current_key
            }
        else:
            # Google AI Studio REST 엔드포인트
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:streamGenerateContent?alt=sse&key={self._current_key}"
            headers = {
                "Content-Type": "application/json"
            }

        # 텍스트·이미지 parts 구성(배치 요청 공통)
        parts = build_google_parts(
            question,
            supports_vision=True,
            wire_format="snake",
            skip_missing=True,
        )

        # PDF 파일 첨부(크기별 인라인·Files API 분기)
        for pdf_path_str in question.pdf_paths:
            path = Path(pdf_path_str)
            if path.exists():
                # 20MB 미만: inline, 그 이상: Files API
                if path.stat().st_size < 20 * 1024 * 1024:
                    mime_type = self._get_mime_type(path)
                    with open(path, 'rb') as f:
                        pdf_data = base64.b64encode(f.read()).decode('utf-8')
                    parts.append({
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": pdf_data
                        }
                    })
                else:
                    # Files API 업로드
                    file_uri = self._upload_file_rest(path)
                    mime_type = self._get_mime_type(path)
                    parts.append({
                        "file_data": {
                            "mime_type": mime_type,
                            "file_uri": file_uri
                        }
                    })

        # 오디오 파일 첨부(Files API)
        for audio_path_str in question.audio_paths:
            path = Path(audio_path_str)
            if path.exists():
                file_uri = self._upload_file_rest(path)
                mime_type = self._get_mime_type(path)
                parts.append({
                    "file_data": {
                        "mime_type": mime_type,
                        "file_uri": file_uri
                    }
                })

        # 동영상 파일 첨부(Files API, 처리 완료 대기)
        for video_path_str in question.video_paths:
            path = Path(video_path_str)
            if path.exists():
                file_uri = self._upload_file_rest(path)
                # 동영상 처리 완료 대기
                self._wait_for_file_active(file_uri)
                mime_type = self._get_mime_type(path)
                parts.append({
                    "file_data": {
                        "mime_type": mime_type,
                        "file_uri": file_uri
                    }
                })

        # Payload 구성
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": parts
                }
            ],
            "generationConfig": {
                "thinkingConfig": {
                    "thinkingLevel": self.config.thinking_level,
                    "includeThoughts": True # 추론 과정 포함 요청
                }
            },
        # 안전 필터 임계값 BLOCK_NONE 설정
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }
        if self.system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": self.system_prompt}]
            }

        # 스트리밍 요청 전송
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=(30, 6000))

        if response.status_code != 200:
            raise Exception(f"API Error {response.status_code}: {response.text}")

        # Server-Sent Events 스트리밍 응답 파싱
        try:
            response_texts = []
            usage_metadata = {}
            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode('utf-8')

                # SSE 외 JSON 배열 응답 처리
                if line.startswith('['):
                    # JSON 배열 전체 파싱
                    chunks = json.loads(line)
                    for chunk_data in chunks:
                        candidates = chunk_data.get('candidates', [])
                        if candidates:
                            content_parts = candidates[0].get('content', {}).get('parts', [])
                            for part in content_parts:
                                if 'text' in part:
                                    response_texts.append(part['text'])
                        # usageMetadata 추출
                        if 'usageMetadata' in chunk_data:
                            usage_metadata = chunk_data['usageMetadata']
                elif line.startswith('data: '):
                    # SSE 형식: "data: {...}"
                    try:
                        data_str = line[6:]  # "data: " 접두사 제거
                        chunk_data = json.loads(data_str)
                        candidates = chunk_data.get('candidates', [])
                        if candidates:
                            content_parts = candidates[0].get('content', {}).get('parts', [])
                            for part in content_parts:
                                if 'text' in part:
                                    response_texts.append(part['text'])
                        # usageMetadata 추출
                        if 'usageMetadata' in chunk_data:
                            usage_metadata = chunk_data['usageMetadata']
                    except json.JSONDecodeError:
                        # JSON 파싱 실패 라인 무시
                        pass

            raw_response = "".join(response_texts)

            # 토큰 사용량 추출
            input_tokens = usage_metadata.get('promptTokenCount')
            output_tokens = usage_metadata.get('candidatesTokenCount')
            thoughts_tokens = usage_metadata.get('thoughtsTokenCount')
            total_tokens = usage_metadata.get('totalTokenCount')
        # 추론 토큰 → 출력 토큰 합산
            if thoughts_tokens and output_tokens:
                output_tokens = output_tokens + thoughts_tokens

            if not raw_response:
            # 스트리밍 응답 없음
                return APIResponse(
                    question_number=question.number,
                    model_name=self.config.name,
                    raw_response="",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    success=False,
                    error_message="No content in streaming response (Safety block?)"
                )

            return APIResponse(
                question_number=question.number,
                model_name=self.config.name,
                raw_response=raw_response,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens
            )

        except Exception as parse_error:
             raise Exception(f"Streaming response parsing failed: {parse_error}")
