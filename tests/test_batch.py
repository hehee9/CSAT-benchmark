"""현대 시험 Batch 수명주기의 집중 검증."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import csat_benchmark.batch as batch_module
from csat_benchmark.batch import (
    BatchError,
    BatchTransport,
    batch_main,
    download_exam,
    status_exam,
    submit_exam,
)
from csat_benchmark.exams import load_exam
from csat_benchmark.models import ModelConfig, Question
from csat_benchmark.runs import model_results_path, model_verified_path


class _FakeBatchTransport(BatchTransport):
    """유료 공급자 호출 없이 Batch 제출·상태·다운로드를 흉내 내는 대역."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.submissions: list[tuple[str, list[dict]]] = []
        self.protocols: list[bool] = []
        self.requests: dict[str, list[dict]] = {}
        self.download_calls: list[str] = []

    def submit(
        self,
        model_config: ModelConfig,
        requests: list[dict],
        *,
        input_path: Path,
        batch_name: str,
        use_responses_api: bool,
    ) -> str:
        del model_config, input_path, batch_name
        batch_id = f"fake-{len(self.submissions) + 1}"
        copied = [dict(request) for request in requests]
        self.submissions.append((batch_id, copied))
        self.protocols.append(use_responses_api)
        self.requests[batch_id] = copied
        return batch_id

    def status(self, batch_id: str, model_config: ModelConfig) -> dict:
        """모든 fake Batch를 즉시 완료 상태로 반환."""
        del model_config
        count = len(self.requests[batch_id])
        return {
            "id": batch_id,
            "status": "completed",
            "request_counts": {"total": count, "completed": count, "failed": 0, "pending": 0},
        }

    def download(self, batch_id: str, model_config: ModelConfig, output_path: Path) -> Path:
        """첫 Batch의 모든 요청을 선택적으로 기술 실패로 반환."""
        del model_config
        self.download_calls.append(batch_id)
        rows = []
        for request in self.requests[batch_id]:
            request_id = request["custom_id"]
            failed = self.fail_first and batch_id == "fake-1"
            rows.append(
                {
                    "request_id": request_id,
                    "success": not failed,
                    "raw_response": f"응답 {batch_id}" if not failed else "기술 실패 진단",
                    "error_message": None if not failed else "공급자 기술 실패",
                    "answer_status": "answered" if not failed else "technical_failure",
                }
            )
        output_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return output_path

    def parse(
        self,
        result_path: Path,
        model_config: ModelConfig,
        *,
        use_responses_api: bool,
        input_requests: list[dict],
    ) -> list[dict]:
        """저장한 fake 응답을 Batch parser 계약으로 반환."""
        del model_config, use_responses_api, input_requests
        return json.loads(result_path.read_text(encoding="utf-8"))


def _write_exam(tmp_path: Path, *, targets: int = 1, questions: int = 2):
    """테스트용 default/easy 시험 매니페스트 생성."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sections = []
    for target_index in range(targets):
        target = f"국어/예시{target_index + 1}"
        section_name = f"예시{target_index + 1}"
        question_records = []
        for number in range(1, questions + 1):
            filename = f"{target_index + 1}-{number}.txt"
            (data_dir / filename).write_text(f"문제 {number}", encoding="utf-8")
            question_records.append(
                {
                    "number": number,
                    "correct_answer": 1,
                    "points": 2,
                    "question_path": filename,
                }
            )
        questions_name = f"questions-{target_index + 1}.json"
        (data_dir / questions_name).write_text(
            json.dumps(
                {"subject": "국어", "section": section_name, "questions": question_records},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        sections.append(
            {
                "target": target,
                "subject": "국어",
                "section": section_name,
                "group": "국어",
                "kind": "common",
                "questions": questions_name,
                "max_points": questions * 2,
            }
        )
    manifest_path = tmp_path / "exam.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "batch-fixture",
                "title": "배치 시험",
                "short_name": "배치 시험",
                "data_dir": "data",
                "results_dir": "results",
                "sections": sections,
                "modes": [
                    {"id": "default", "label": "일반", "input_mode": "section"},
                    {"id": "easy", "label": "쉬움", "input_mode": "question"},
                ],
                "publish": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return load_exam(manifest_path, project_root=tmp_path)


def _write_config(tmp_path: Path, names: list[str]) -> Path:
    """테스트용 모델 설정 작성."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "system_prompt": "공통 배치 지시",
                "models": [
                    {
                        "name": name,
                        "api_type": "openai",
                        "api_key_env": "BATCH_TEST_KEY",
                        "model_id": f"mock-{index}",
                        "batch_supported": True,
                    }
                    for index, name in enumerate(names)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config_path


def test_default_and_easy_submit_once_per_key(tmp_path: Path, monkeypatch):
    """default는 section 한 번, easy는 문항별 한 번만 제출한다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=2)
    config_path = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()

    normal = submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    easy = submit_exam(
        exam,
        config_path=config_path,
        easy=True,
        model_names=["모의 모델"],
        transport=transport,
    )

    assert normal["submitted"] == 1
    assert easy["submitted"] == 2
    assert normal["run"]["input_mode"] == "section"
    assert easy["run"]["input_mode"] == "question"
    assert len(transport.submissions) == 2
    assert len(transport.submissions[0][1]) == 1
    assert len(transport.submissions[1][1]) == 2
    assert "run_id" not in normal["run"]
    assert all("attempt" not in job for job in normal["batch_state"]["jobs"])


def test_batch_lifecycle_retries_only_technical_failure(tmp_path: Path, monkeypatch):
    """기술 실패만 재시도하고 완료 결과와 provider ID 수명주기를 보존한다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config_path = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport(fail_first=True)

    submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    first_download = download_exam(exam, config_path=config_path, transport=transport)
    assert first_download["saved_results"] == 1
    assert first_download["run"]["results"][0]["success"] is False

    retried = submit_exam(
        exam,
        config_path=config_path,
        model_names=["모의 모델"],
        retry_failed=True,
        transport=transport,
    )
    assert retried["submitted"] == 1
    assert len(transport.submissions) == 2
    assert transport.protocols == [False, False]
    assert all("run_id" not in job and "attempt" not in job for job in retried["batch_state"]["jobs"])

    with pytest.raises(BatchError, match="처리 중인 batch"):
        submit_exam(
            exam,
            config_path=config_path,
            model_names=["모의 모델"],
            retry_failed=True,
            transport=transport,
        )
    completed = download_exam(exam, config_path=config_path, transport=transport)
    assert completed["run"]["results"][0]["success"] is True
    assert {job["provider_batch_id"] for job in completed["batch_state"]["jobs"]} == {"fake-1", "fake-2"}


def test_ordinary_submit_replaces_completed_key(tmp_path: Path, monkeypatch):
    """일반 제출은 완료 결과도 선택 key에 대해 새 Batch로 교체한다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config_path = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    download_exam(exam, config_path=config_path, transport=transport)
    replacement = submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    assert replacement["submitted"] == 1
    assert len(transport.submissions) == 2


def test_active_overlap_is_per_target_model_key(tmp_path: Path, monkeypatch):
    """활성 중복은 target·모델·문항 key만 막고 다른 key는 허용한다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, targets=2, questions=1)
    config_path = _write_config(tmp_path, ["모델 A", "모델 B"])
    transport = _FakeBatchTransport()
    submit_exam(
        exam,
        config_path=config_path,
        model_names=["모델 A"],
        targets=["국어/예시1"],
        transport=transport,
    )
    submit_exam(
        exam,
        config_path=config_path,
        model_names=["모델 B"],
        targets=["국어/예시1"],
        transport=transport,
    )
    submit_exam(
        exam,
        config_path=config_path,
        model_names=["모델 A"],
        targets=["국어/예시2"],
        transport=transport,
    )
    with pytest.raises(BatchError, match="처리 중인 batch"):
        submit_exam(
            exam,
            config_path=config_path,
            model_names=["모델 A"],
            targets=["국어/예시1"],
            transport=transport,
        )
    assert len(transport.submissions) == 3


def test_verified_only_key_is_skipped_without_creating_raw_sidecar(tmp_path: Path, monkeypatch):
    """verified-only 완료 범위는 재시도하지 않고 raw 파일을 만들지 않는다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=2)
    config_path = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    initial = submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    index = Path(initial["path"])
    raw_path = model_results_path(index, "모의 모델")
    raw_path.unlink()
    model_verified_path(index, "모의 모델").write_text(
        json.dumps(
            {
                "exam_id": exam.id,
                "mode": "default",
                "model_name": "모의 모델",
                "results": [
                    {"target": "국어/예시1", "model_name": "모의 모델", "question_number": 1, "complete": True},
                    {"target": "국어/예시1", "model_name": "모의 모델", "question_number": 2, "complete": True},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    retried = submit_exam(
        exam,
        config_path=config_path,
        model_names=["모의 모델"],
        retry_failed=True,
        transport=transport,
    )
    assert retried["submitted"] == 0
    assert not raw_path.exists()
    assert retried["batch_state"]["jobs"]
    assert not any("attempt" in job for job in retried["batch_state"]["jobs"])


def test_old_terminal_download_cannot_overwrite_new_replacement(tmp_path: Path, monkeypatch):
    """이전 terminal Batch 결과가 뒤의 명시적 재제출 결과를 덮어쓰지 않는다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config_path = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    status_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    replacement = submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    downloaded = download_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    assert replacement["submitted"] == 1
    assert downloaded["saved_results"] == 1
    assert downloaded["run"]["results"][0]["raw_response"] == "응답 fake-2"
    assert {job["provider_batch_id"] for job in downloaded["batch_state"]["jobs"]} == {"fake-1", "fake-2"}


def test_download_filter_reuses_raw_and_preserves_unselected_scope(tmp_path: Path, monkeypatch):
    """분할 다운로드는 raw를 재사용하고 다른 target 결과를 먼저 쓰지 않는다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, targets=2, questions=1)
    config_path = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    submit_exam(
        exam,
        config_path=config_path,
        model_names=["모의 모델"],
        targets=["국어/예시1", "국어/예시2"],
        transport=transport,
    )
    first = download_exam(
        exam,
        config_path=config_path,
        model_names=["모의 모델"],
        targets=["국어/예시1"],
        transport=transport,
    )
    assert {row["target"] for row in first["run"]["results"]} == {"국어/예시1"}
    assert first["batch_state"]["jobs"][0]["downloaded"] is False
    assert transport.download_calls == ["fake-1"]

    second = download_exam(
        exam,
        config_path=config_path,
        model_names=["모의 모델"],
        targets=["국어/예시2"],
        transport=transport,
    )
    assert {row["target"] for row in second["run"]["results"]} == {
        "국어/예시1",
        "국어/예시2",
    }
    assert transport.download_calls == ["fake-1"]
    assert second["batch_state"]["jobs"][0]["downloaded"] is True


def test_each_new_job_can_select_a_different_protocol(tmp_path: Path, monkeypatch):
    """새 Batch는 기존 job과 별개로 Chat 또는 Responses API를 선택한다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    exam = _write_exam(tmp_path, questions=1)
    config_path = _write_config(tmp_path, ["모의 모델"])
    transport = _FakeBatchTransport()
    submit_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    status_exam(exam, config_path=config_path, model_names=["모의 모델"], transport=transport)
    submit_exam(
        exam,
        config_path=config_path,
        model_names=["모의 모델"],
        use_responses_api=True,
        transport=transport,
    )
    assert transport.protocols == [False, True]


def test_batch_rejects_unsupported_media_before_run_or_submit(tmp_path: Path, monkeypatch):
    """배치 미지원 PDF를 실행 기록·공급자 전송 전에 거부한다."""
    monkeypatch.setenv("BATCH_TEST_KEY", "test-key")
    config_path = _write_config(tmp_path, ["모의 모델"])
    exam = load_exam("example-text")
    target = exam.sections[0].target
    question = Question(number=1, correct_answer=1, points=2, question_text="본문", pdf_paths=[str(tmp_path / "문서.pdf")])
    monkeypatch.setattr(
        batch_module,
        "_prepare_sections",
        lambda manifest, sections, mode, question_numbers: ([], {target: [(question, 1)]}),
    )
    with patch.object(batch_module, "create_run", side_effect=AssertionError("실행 기록 생성 금지")):
        with pytest.raises(ValueError, match="PDF"):
            submit_exam(
                exam,
                config_path=config_path,
                model_names=["모의 모델"],
                output=tmp_path / "run" / "results.json",
                transport=_FakeBatchTransport(),
            )


def test_batch_cli_requires_exam_and_removes_old_run_mode_hard_flags():
    """Batch CLI는 --exam을 요구하고 구형 실행 식별자·mode·hard를 받지 않는다."""
    with pytest.raises(SystemExit):
        batch_main([])
    for flag in ("--run", "--mode", "--hard"):
        with pytest.raises(SystemExit):
            batch_main(["--exam", "example-text", flag, "old"])
