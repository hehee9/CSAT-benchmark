"""단일 실행 검증 결과의 공개·Excel 변환 집중 검증."""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

from csat_benchmark.evaluation import grade_run, load_verified, save_verified
from csat_benchmark.exams import load_exam
from csat_benchmark.exports import (
    _merge_token_scope,
    _new_token_record,
    _write_json,
    _write_json_if_changed,
    export_run_to_excel,
    import_excel_corrections,
    publish_run,
)
from csat_benchmark.runs import (
    canonical_results_path, create_run, invalidate_verified_results,
    model_verified_path, save_run,
)
from sync_data import DataConverter, ExcelHandler, ModelNameMapper, PathMapper


def _publish_process(barrier, manifest_path: str, output_dir: str, run, verified) -> None:
    """@description 동시 공개 회귀 검증을 위해 별도 프로세스에서 시험 결과 공개"""
    barrier.wait(timeout=30)
    exam = load_exam(manifest_path, project_root=Path(manifest_path).parent)
    publish_run(exam, run, verified, output_dir=output_dir, targets=run["selected_targets"])


def _make_parallel_publish_exam(tmp_path: Path):
    """@description 병렬 공개 검증용 두 target 시험 및 모델 입력 생성"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sections = []
    targets = [("국어/예시1", "국어", "예시1"), ("수학/예시2", "수학", "예시2")]
    for target, subject, section in targets:
        section_dir = data_dir / section
        section_dir.mkdir()
        (section_dir / "questions.json").write_text(
            json.dumps(
                {
                    "subject": subject,
                    "section": section,
                    "questions": [
                        {"number": 1, "correct_answer": 2, "points": 2, "question_path": "1.txt"},
                        {"number": 2, "correct_answer": 1, "points": 2, "question_path": "2.txt"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (section_dir / "1.txt").write_text("첫 번째 문항", encoding="utf-8")
        (section_dir / "2.txt").write_text("두 번째 문항", encoding="utf-8")
        sections.append(
            {
                "target": target,
                "subject": subject,
                "section": section,
                "group": subject,
                "kind": "common",
                "questions": f"{section}/questions.json",
                "max_points": 4,
            }
        )
    manifest_path = tmp_path / "exam.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "parallel-publish-test",
                "title": "병렬 공개 시험",
                "short_name": "병렬 공개 시험",
                "exam_month": None,
                "data_dir": "data",
                "results_dir": "results",
                "publish": True,
                "sections": sections,
                "modes": [{"id": "default", "label": "default", "input_mode": "section"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    exam = load_exam(manifest_path, project_root=tmp_path)
    inputs = []
    for (target, subject, section), model_name, cutoff in zip(
        targets,
        ("모델 A", "모델 B"),
        ("2025-01", "2025-02"),
    ):
        timestamp = "2026-09-08T00:00:00+00:00"
        run = create_run(
            exam_id=exam.id,
            mode="default",
            input_mode="section",
            selected_targets=[target],
            selected_models=[
                {"name": model_name, "price": {"input": 1.0}, "knowledge_cutoff": cutoff}
            ],
            input_context=[{"target": target, "question_numbers": [1, 2]}],
        )
        run["results"].append(
            {
                "target": target,
                "subject": subject,
                "section": section,
                "model_name": model_name,
                "question_number": 0,
                "raw_response": "2,1",
                "timestamp": timestamp,
                "success": True,
                "error_message": None,
                "input_tokens": 5,
                "output_tokens": 7,
                "total_tokens": 12,
                "answer_status": None,
                "provider_stop_reason": None,
                "error_details": None,
            }
        )
        verified = {
            "schema_version": 1,
            "exam_id": exam.id,
            "mode": "default",
            "selected_models": [model_name],
            "results": [
                {
                    "target": target,
                    "subject": subject,
                    "section": section,
                    "model_name": model_name,
                    "question_number": number,
                    "extracted_answer": answer,
                    "correct_answer": correct,
                    "is_correct": answer == correct,
                    "points": 2,
                    "answer_status": "answered",
                    "provider_stop_reason": None,
                    "complete": True,
                    "provenance": "graded",
                    "raw_response": "2,1",
                    "timestamp": timestamp,
                }
                for number, answer, correct in ((1, 2, 2), (2, 1, 1))
            ],
        }
        inputs.append((run, verified))
    return manifest_path, exam, inputs


class _SectionVerifier:
    """섹션 응답에 고정된 문항별 답을 반환하는 검증기 대역."""

    model_id = "test-verifier"
    reasoning_effort = "low"

    def verify_hard_answers(self, raw_response, question_infos):
        answers = [int(value) for value in raw_response.split(",")]
        return [
            {
                "question_number": info["number"],
                "correct_answer": info["correct_answer"],
                "llm_answer": answers[index],
            }
            for index, info in enumerate(question_infos)
        ]


class _QuestionVerifier:
    """문항별 응답을 정수 답으로 변환하는 검증기 대역."""

    model_id = "test-verifier"
    reasoning_effort = "low"

    def verify_answer(self, raw_response, correct_answer, question_number, question_text):
        return int(raw_response)


def test_grading_only_saves_new_rows_and_reused_rows_stay_invalidated(tmp_path: Path):
    """@description 실제 채점 결과의 신규 행 추적과 재사용 행 부활 방지"""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section")
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    first = grade_run(index, exam, _SectionVerifier())
    assert len(first["graded_keys"]) == 2
    save_verified(first, index)
    reused = grade_run(index, exam, _SectionVerifier())
    assert len(reused["results"]) == 2
    assert reused["graded_keys"] == []
    invalidate_verified_results(index, "모의 모델", "국어/예시", 0, input_mode="section", question_numbers=[1, 2])
    save_verified(reused, index)
    assert json.loads(model_verified_path(index, "모의 모델").read_text(encoding="utf-8"))["results"] == []


def test_invalidation_while_section_verifier_runs_discards_newly_graded_rows(tmp_path: Path):
    """@description 추출기 실행 중 무효화된 실제 채점 결과 저장 차단"""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section")
    index = canonical_results_path(exam, "default")
    save_run(run, index)

    class _InvalidatingVerifier(_SectionVerifier):
        """@description 답안 추출 중 원본 재생성 시작을 모의하는 검증기"""

        def verify_hard_answers(self, raw_response, question_infos):
            invalidate_verified_results(index, "모의 모델", "국어/예시", 0, input_mode="section", question_numbers=[1, 2])
            return super().verify_hard_answers(raw_response, question_infos)

    graded = grade_run(index, exam, _InvalidatingVerifier())
    assert len(graded["graded_keys"]) == 2
    save_verified(graded, index)
    assert json.loads(model_verified_path(index, "모의 모델").read_text(encoding="utf-8"))["results"] == []


def test_mapping_based_grading_saves_to_fresh_destination(tmp_path: Path):
    """@description 원본 파일 없는 메모리 실행 채점 결과의 새 경로 저장 보존"""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section")
    graded = grade_run(run, exam, _SectionVerifier())
    assert len(graded["graded_keys"]) == 2
    assert graded["raw_index_path"] is None
    output = tmp_path / "alternate" / "results.json"
    save_verified(graded, output)
    assert load_verified(model_verified_path(output, "모의 모델"))["results"] == graded["results"]


def test_alternate_output_snapshots_current_source_reused_rows(tmp_path: Path):
    """@description 별도 출력은 재사용 행의 최신 원본 검증 상태를 복사하고 무효화 반영"""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section")
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    save_verified(grade_run(index, exam, _SectionVerifier()), index)
    reused = grade_run(index, exam, _SectionVerifier())
    assert reused["graded_keys"] == []
    latest = load_verified(index)
    latest["results"][0]["extracted_answer"] = 4
    latest["results"][0]["is_correct"] = False
    save_verified(latest, index)
    output = tmp_path / "alternate" / "results.json"
    save_verified(reused, output)
    assert load_verified(model_verified_path(output, "모의 모델"))["results"] == latest["results"]
    invalidate_verified_results(index, "모의 모델", "국어/예시", 0, input_mode="section", question_numbers=[1, 2])
    save_verified(reused, output)
    assert load_verified(model_verified_path(output, "모의 모델"))["results"] == []


def test_alternate_output_rejects_source_invalidated_during_grading(tmp_path: Path, capsys):
    """@description 별도 출력의 빈 검증 기록과 무관하게 원본 무효화로 저장 차단"""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section")
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    graded = grade_run(index, exam, _SectionVerifier())
    invalidate_verified_results(index, "모의 모델", "국어/예시", 0, input_mode="section", question_numbers=[1, 2])
    output = tmp_path / "alternate" / "results.json"
    save_verified(graded, output)
    assert load_verified(model_verified_path(output, "모의 모델"))["results"] == []
    assert "2개 저장 건너뜀 (채점 시작 후 원본 무효화)" in capsys.readouterr().out


def _make_exam(tmp_path: Path, *, mode: str = "default", input_mode: str = "section"):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    questions = [
        {"number": 1, "correct_answer": 2, "points": 2, "question_path": "1.txt"},
        {"number": 2, "correct_answer": 1, "points": 2, "question_path": "2.txt"},
    ]
    (data_dir / "questions.json").write_text(
        json.dumps({"subject": "국어", "section": "예시", "questions": questions}, ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "1.txt").write_text("첫 번째 문항", encoding="utf-8")
    (data_dir / "2.txt").write_text("두 번째 문항", encoding="utf-8")
    manifest_path = tmp_path / "exam.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "exports-test",
                "title": "변환 시험",
                "short_name": "변환 시험",
                "exam_month": None,
                "data_dir": "data",
                "results_dir": "results",
                "publish": True,
                "sections": [
                    {
                        "target": "국어/예시",
                        "subject": "국어",
                        "section": "예시",
                        "group": "국어",
                        "kind": "common",
                        "questions": "questions.json",
                        "max_points": 4,
                    }
                ],
                "modes": [{"id": mode, "label": mode, "input_mode": input_mode}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return load_exam(manifest_path, project_root=tmp_path)


def _make_run(exam, *, mode: str, input_mode: str, model: str = "모의 모델", raw: str = "2,1", success: bool = True):
    run = create_run(
        exam_id=exam.id,
        mode=mode,
        input_mode=input_mode,
        selected_targets=["국어/예시"],
        selected_models=[{"name": model, "price": {"input": 1.0}}],
        input_context=[{"target": "국어/예시", "question_numbers": [1, 2]}],
    )
    run["results"].append(
        {
            "target": "국어/예시",
            "subject": "국어",
            "section": "예시",
            "model_name": model,
            "question_number": 0 if input_mode == "section" else 1,
            "raw_response": raw if success else "",
            "timestamp": "2026-09-08T00:00:00+00:00",
            "success": success,
            "error_message": None if success else "기술 실패",
            "input_tokens": 5,
            "output_tokens": 7,
            "total_tokens": 12,
            "answer_status": None,
            "provider_stop_reason": None,
            "error_details": None,
        }
    )
    return run


def test_single_run_flat_public_and_excel_round_trip(tmp_path: Path):
    """단일 응답이 flat verified 행·모델 한 열·공개 결과로 변환된다."""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section")
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    verified = grade_run(index, exam, _SectionVerifier())
    assert all("attempts" not in row for row in verified["results"])
    save_verified(verified, index)

    excel_path = export_run_to_excel(index, tmp_path / "answers.xlsx", run=index, exam=exam)
    worksheet = load_workbook(excel_path)["국어-예시"]
    assert [cell.value for cell in worksheet[1]] == ["문항 번호", "정답", "배점", "모의 모델"]
    worksheet["D2"] = 1
    worksheet.parent.save(excel_path)
    imported = import_excel_corrections(index, excel_path, run=index, exam=exam)
    assert imported["changed"] == 1
    assert imported["verified"]["results"][0]["provenance"] == "excel_manual"
    assert imported["verified"]["results"][0]["is_correct"] is False

    paths = publish_run(exam, index, index, output_dir=tmp_path / "published")
    public = json.loads(paths["results"].read_text(encoding="utf-8"))
    assert public[0]["score"] == 2
    assert "run_id" not in public[0]
    assert all("attempts" not in item for item in public[0]["results"])
    token = json.loads(paths["token_usage"].read_text(encoding="utf-8"))
    assert token["models"]["모의 모델"]["sections"]["국어-예시"]["total_tokens"] == 12
    assert token["models"]["모의 모델"]["sections"]["국어-예시"]["last_updated"] == "2026-09-08T00:00:00+00:00"
    assert token["models"]["모의 모델"]["last_updated"] == "2026-09-08T00:00:00+00:00"


def test_atomic_json_writer_preserves_format_and_removes_temp_files(tmp_path: Path, monkeypatch):
    """@description 원자적 JSON 저장의 기존 바이트 형식과 unchanged 생략 확인"""
    path = tmp_path / "public.json"
    payload = {"모델": {"description": "한국어", "values": [1, 2]}}
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    expected = expected_path.read_bytes()

    _write_json(path, payload)

    assert path.read_bytes() == expected
    assert list(tmp_path.glob(".*.tmp")) == []

    def unexpected_replace(*_args):
        raise AssertionError("unchanged JSON must skip replacement")

    monkeypatch.setattr("csat_benchmark.exports.os.replace", unexpected_replace)
    _write_json_if_changed(path, payload)
    assert path.read_bytes() == expected
    assert list(tmp_path.glob(".*.tmp")) == []


def test_parallel_publish_merges_disjoint_groups_across_processes(tmp_path: Path):
    """@description 별도 프로세스의 동시 공개가 결과·토큰·문항·모델 메타데이터를 보존"""
    manifest_path, exam, inputs = _make_parallel_publish_exam(tmp_path)
    output_dir = tmp_path / "published"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes = [
        context.Process(
            target=_publish_process,
            args=(barrier, str(manifest_path), str(output_dir), run, verified),
        )
        for run, verified in inputs
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=45)
        assert all(not process.is_alive() for process in processes)
        assert [process.exitcode for process in processes] == [0, 0]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()

    records = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
    record_keys = {(record["target"], record["model_name"]) for record in records}
    assert record_keys == {("국어/예시1", "모델 A"), ("수학/예시2", "모델 B")}

    tokens = json.loads((output_dir / "token_usage.json").read_text(encoding="utf-8"))
    assert tokens["models"]["모델 A"]["sections"]["국어-예시1"]["total_tokens"] == 12
    assert tokens["models"]["모델 B"]["sections"]["수학-예시2"]["total_tokens"] == 12

    questions = json.loads((output_dir / "questions_metadata.json").read_text(encoding="utf-8"))
    assert questions["국어-예시1"] == {
        "1": {"hasImage": False, "points": 2},
        "2": {"hasImage": False, "points": 2},
    }
    assert questions["수학-예시2"] == {
        "1": {"hasImage": False, "points": 2},
        "2": {"hasImage": False, "points": 2},
    }

    model_metadata = json.loads(
        (exam.project_root / "web" / "model_metadata.json").read_text(encoding="utf-8")
    )
    assert model_metadata["모델 A"]["knowledgeCutoff"] == "2025-01"
    assert model_metadata["모델 B"]["knowledgeCutoff"] == "2025-02"


def test_existing_workbook_preserves_unselected_cells_and_styles(tmp_path: Path):
    """기존 동적 헤더 Excel에서는 선택 열만 갱신한다."""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section")
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    save_verified(grade_run(index, exam, _SectionVerifier()), index)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "국어-예시"
    worksheet["A1"] = "기존 제목"
    worksheet["A1"].fill = PatternFill(fill_type="solid", fgColor="FFFF00")
    worksheet["A2"] = "문항 번호"
    worksheet["B2"] = "정답"
    worksheet["C2"] = "기존 모델"
    worksheet["D2"] = "모의 모델"
    worksheet["A3"] = 1
    worksheet["B3"] = 2
    worksheet["C3"] = 9
    worksheet["D3"] = 9
    worksheet["A4"] = 2
    worksheet["B4"] = 1
    worksheet["C4"] = 8
    worksheet["D4"] = 8
    worksheet["A5"] = "총점"
    worksheet["C5"] = 17
    worksheet["D5"] = 17
    original_fill = worksheet["A1"].fill.fgColor.rgb
    excel_path = tmp_path / "existing.xlsx"
    workbook.save(excel_path)
    export_run_to_excel(index, excel_path, run=index, exam=exam, model_names=["모의 모델"])
    updated = load_workbook(excel_path)["국어-예시"]
    assert updated["A1"].value == "기존 제목"
    assert updated["A1"].fill.fgColor.rgb == original_fill
    assert updated["C3"].value == 9
    assert updated["D3"].value == 2


def test_excel_export_writes_totals_and_status_labels_without_replacing_formulas(tmp_path: Path):
    """새 Excel과 기존 literal 총점을 갱신하고 총점 수식은 보존한다."""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="question")
    run["selected_models"].append({"name": "다른 모델", "price": {"input": 1.0}})
    verified = {
        "selected_models": ["모의 모델", "다른 모델"],
        "selected_targets": ["국어/예시"],
        "results": [
            {
                "target": "국어/예시",
                "model_name": "모의 모델",
                "question_number": 1,
                "extracted_answer": 2,
                "is_correct": True,
                "points": 2,
            },
            {
                "target": "국어/예시",
                "model_name": "모의 모델",
                "question_number": 2,
                "extracted_answer": -1,
                "is_correct": False,
                "points": 2,
            },
            {
                "target": "국어/예시",
                "model_name": "다른 모델",
                "question_number": 1,
                "extracted_answer": 1,
                "is_correct": False,
                "points": 2,
            },
            {
                "target": "국어/예시",
                "model_name": "다른 모델",
                "question_number": 2,
                "extracted_answer": -2,
                "is_correct": False,
                "points": 2,
            },
        ],
    }

    new_path = export_run_to_excel(verified, tmp_path / "new.xlsx", run=run, exam=exam)
    new_sheet = load_workbook(new_path, data_only=False)["국어-예시"]
    assert new_sheet["D2"].value == 2
    assert new_sheet["D3"].value == "(포기)"
    assert new_sheet["D3"].number_format == "General"
    assert new_sheet["D4"].value == 2
    assert new_sheet["E3"].value == "(검열)"
    assert new_sheet["E3"].number_format == "General"
    assert new_sheet["E4"].value == 0

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "국어-예시"
    worksheet.append(["문항 번호", "정답", "모의 모델", "다른 모델"])
    worksheet.append([1, 2, 9, 9])
    worksheet.append([2, 1, 8, 8])
    worksheet.append(["총점", None, "=SUM(C2:C3)", 99])
    existing_path = tmp_path / "existing_totals.xlsx"
    workbook.save(existing_path)

    export_run_to_excel(verified, existing_path, run=run, exam=exam)
    existing_sheet = load_workbook(existing_path, data_only=False)["국어-예시"]
    assert existing_sheet["C4"].value == "=SUM(C2:C3)"
    assert existing_sheet["D4"].value == 0


def test_imported_public_noop_preserves_public_and_tokens(tmp_path: Path):
    """raw 없는 imported_public 재공개는 기존 결과·토큰을 그대로 보존한다."""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section", success=False)
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    imported_rows = [
        {
            "target": "국어/예시",
            "subject": "국어",
            "section": "예시",
            "model_name": "모의 모델",
            "question_number": 1,
            "extracted_answer": 2,
            "correct_answer": 2,
            "is_correct": True,
            "points": 2,
            "answer_status": "answered",
            "complete": True,
            "provenance": "imported_public",
        },
        {
            "target": "국어/예시",
            "subject": "국어",
            "section": "예시",
            "model_name": "모의 모델",
            "question_number": 2,
            "extracted_answer": 1,
            "correct_answer": 1,
            "is_correct": True,
            "points": 2,
            "answer_status": "answered",
            "complete": True,
            "provenance": "imported_public",
        },
    ]
    save_verified(
        {"schema_version": 1, "exam_id": exam.id, "mode": "default", "selected_models": ["모의 모델"], "results": imported_rows},
        index,
    )
    output = tmp_path / "published"
    output.mkdir()
    old_results = [{"sheet_name": "국어-예시", "subject": "국어", "section": "예시", "model_name": "모의 모델", "score": 4, "results": []}]
    old_tokens = {"models": {"모의 모델": {"total_tokens": 99, "sections": {"국어-예시": {"total_tokens": 99}}}}}
    results_path = output / "results.json"
    tokens_path = output / "token_usage.json"
    results_path.write_bytes((json.dumps(old_results, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8"))
    tokens_path.write_bytes((json.dumps(old_tokens, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8"))
    old_results_bytes = results_path.read_bytes()
    old_tokens_bytes = tokens_path.read_bytes()
    publish_run(exam, index, index, output_dir=output)
    assert results_path.read_bytes() == old_results_bytes
    assert tokens_path.read_bytes() == old_tokens_bytes


def test_incomplete_verified_scope_is_not_published(tmp_path: Path):
    """기술 실패로 남은 verified 행은 공개를 거부한다."""
    exam = _make_exam(tmp_path)
    run = _make_run(exam, mode="default", input_mode="section", success=False)
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    save_verified(grade_run(index, exam, _SectionVerifier()), index)
    with pytest.raises(ValueError, match="정본 원본이 없는 stale graded"):
        publish_run(exam, index, index, output_dir=tmp_path / "published")


def test_publish_preserves_legacy_tokens_and_marks_fresh_unknown_usage(tmp_path: Path):
    """Excel 수동 수정 범위의 기존 토큰을 보존하고 새 미상 사용량은 None으로 기록한다."""
    exam = _make_exam(tmp_path)
    legacy_model = "Claude Opus 4.7 (high)"
    fresh_model = "새 모델"
    run = _make_run(exam, mode="default", input_mode="section", model=legacy_model)
    run["selected_models"].append({"name": fresh_model, "price": {"input": 1.0}})
    run["results"][0].pop("input_tokens")
    run["results"][0].pop("output_tokens")
    run["results"][0].pop("total_tokens")
    run["results"].append(
        {
            "target": "국어/예시",
            "subject": "국어",
            "section": "예시",
            "model_name": fresh_model,
            "question_number": 0,
            "raw_response": "2,1",
            "timestamp": "2026-09-08T00:00:00+00:00",
            "success": True,
            "error_message": None,
            "answer_status": None,
            "provider_stop_reason": None,
            "error_details": None,
        }
    )
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    verified_rows = []
    for model, provenance in ((legacy_model, "imported_public"), (fresh_model, "graded")):
        verified_rows.extend(
            {
                "target": "국어/예시",
                "subject": "국어",
                "section": "예시",
                "model_name": model,
                "question_number": number,
                "extracted_answer": answer,
                "correct_answer": correct,
                "is_correct": answer == correct,
                "points": 2,
                "answer_status": "answered",
                "provider_stop_reason": None,
                "needs_manual_review": False,
                "complete": True,
                "raw_response": "2,1" if provenance == "graded" else "",
                "timestamp": "2026-09-08T00:00:00+00:00" if provenance == "graded" else None,
                "provenance": provenance,
            }
            for number, answer, correct in ((1, 2, 2), (2, 1, 1))
        )
    save_verified(
        {
            "schema_version": 1,
            "exam_id": exam.id,
            "mode": "default",
            "selected_models": [legacy_model, fresh_model],
            "results": verified_rows,
        },
        index,
    )
    excel_path = export_run_to_excel(index, tmp_path / "answers.xlsx", run=index, exam=exam)
    workbook = load_workbook(excel_path)
    workbook["국어-예시"]["D2"] = 1
    workbook.save(excel_path)
    workbook.close()
    import_excel_corrections(index, excel_path, run=index, exam=exam)

    legacy_section = {
        "input_tokens": 101,
        "output_tokens": 202,
        "total_tokens": 303,
        "question_count": 2,
        "last_updated": "legacy-section",
        "custom": "keep",
    }
    unrelated_model = {
        "total_input_tokens": 7,
        "total_output_tokens": 8,
        "total_tokens": 15,
        "question_count": 1,
        "sections": {"다른 섹션": {"input_tokens": 7, "output_tokens": 8, "total_tokens": 15}},
    }
    old_tokens = {
        "models": {
            legacy_model: {
                "total_input_tokens": 101,
                "total_output_tokens": 202,
                "total_tokens": 303,
                "question_count": 2,
                "last_updated": "legacy-model",
                "sections": {"국어-예시": legacy_section},
            },
            "관계없는 모델": unrelated_model,
        }
    }
    output = tmp_path / "published"
    output.mkdir()
    (output / "results.json").write_text("[]\n", encoding="utf-8")
    (output / "token_usage.json").write_text(
        json.dumps(old_tokens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    publish_run(exam, index, index, output_dir=output)
    tokens = json.loads((output / "token_usage.json").read_text(encoding="utf-8"))
    assert tokens["models"][legacy_model] == old_tokens["models"][legacy_model]
    assert tokens["models"]["관계없는 모델"] == unrelated_model
    assert tokens["models"][fresh_model]["sections"]["국어-예시"] == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "question_count": 1,
        "last_updated": "2026-09-08T00:00:00+00:00",
    }
    assert tokens["models"][fresh_model]["total_input_tokens"] is None
    assert tokens["models"][fresh_model]["total_output_tokens"] is None
    assert tokens["models"][fresh_model]["total_tokens"] is None


def test_token_usage_dates_propagate_latest_section_and_preserve_legacy_date():
    """@description 여러 섹션의 최신 날짜를 모델에 반영하고 날짜 없는 원본의 기존 날짜 보존"""
    latest = "2026-09-08 20:52:10"
    older = "2026-09-07 20:52:10"
    source_record = _new_token_record(
        [
            {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3, "timestamp": latest},
            {"input_tokens": 4, "output_tokens": 5, "total_tokens": 6, "timestamp": older},
        ]
    )
    legacy_record = {
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
        "question_count": 1,
        "last_updated": older,
    }
    merged = _merge_token_scope(
        {
            "models": {
                "모델": {
                    "last_updated": latest,
                    "sections": {
                        "최신 섹션": {
                            "input_tokens": 7,
                            "output_tokens": 8,
                            "total_tokens": 15,
                            "question_count": 1,
                            "last_updated": latest,
                        },
                        "기존 섹션": legacy_record,
                    },
                }
            }
        },
        {
            ("모델", "기존 섹션"): _new_token_record(
                [{"input_tokens": 11, "output_tokens": 22, "total_tokens": 33}]
            ),
            ("모델", "새 섹션"): source_record,
        },
    )

    model = merged["models"]["모델"]
    assert source_record["last_updated"] == latest
    assert model["sections"]["기존 섹션"]["last_updated"] == older
    assert model["sections"]["새 섹션"]["last_updated"] == latest
    assert model["last_updated"] == latest


def test_multiple_correct_answers_round_trip_through_canonical_excel_and_public_json(tmp_path: Path):
    """복수 정답 대안이 Excel 표시·수동 재채점·공개 JSON에서 보존된다."""
    exam = _make_exam(tmp_path)
    questions_path = exam.data_root / "questions.json"
    payload = json.loads(questions_path.read_text(encoding="utf-8"))
    payload["questions"][0]["correct_answer"] = [2, 3]
    questions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    exam = load_exam(exam.manifest_path, project_root=tmp_path)

    run = _make_run(exam, mode="default", input_mode="section", raw="3,1")
    index = canonical_results_path(exam, "default")
    save_run(run, index)
    verified = grade_run(index, exam, _SectionVerifier())
    save_verified(verified, index)

    excel_path = export_run_to_excel(index, tmp_path / "answers.xlsx", run=index, exam=exam)
    worksheet = load_workbook(excel_path)["국어-예시"]
    assert worksheet["B2"].value == "2, 3"
    assert worksheet["D2"].value == 3

    worksheet["B2"] = 9
    worksheet.parent.save(excel_path)
    export_run_to_excel(index, excel_path, run=index, exam=exam)
    worksheet = load_workbook(excel_path)["국어-예시"]
    assert worksheet["B2"].value == "2, 3"

    worksheet["D2"] = 2
    worksheet.parent.save(excel_path)
    imported = import_excel_corrections(index, excel_path, run=index, exam=exam)
    imported_row = next(row for row in imported["verified"]["results"] if row["question_number"] == 1)
    assert imported_row["correct_answer"] == [2, 3]
    assert imported_row["is_correct"] is True

    paths = publish_run(exam, index, imported["path"], output_dir=tmp_path / "published")
    public = json.loads(paths["results"].read_text(encoding="utf-8"))
    public_row = public[0]["results"][0]
    assert public_row["correct_answer"] == [2, 3]
    assert public[0]["score"] == 4


def test_legacy_excel_json_round_trip_scores_multiple_answers_and_statuses(tmp_path: Path):
    """legacy Excel·JSON 변환이 복수 정답, 오답, 포기 답안을 구분한다."""
    questions_dir = tmp_path / "problems" / "국어" / "공통"
    questions_dir.mkdir(parents=True)
    (questions_dir / "questions.json").write_text(
        json.dumps(
            {
                "subject": "국어",
                "section": "공통",
                "questions": [
                    {"number": 1, "correct_answer": [2, 3], "points": 2},
                    {"number": 2, "correct_answer": 1, "points": 2},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "국어-공통"
    worksheet.append(["문항 번호", "정답", "모델"])
    worksheet.append([1, "2, 3", 3])
    worksheet.append([2, 1, "(포기)"])
    worksheet.append(["총점", None, 2])
    excel_path = tmp_path / "legacy.xlsx"
    workbook.save(excel_path)

    handler = ExcelHandler(excel_path)
    answers = handler.get_model_answers("국어-공통", "모델")
    assert handler._get_correct_answers("국어-공통") == {1: [2, 3], 2: 1}
    handler._load_questions_for_sheet = lambda _sheet: {
        "questions": [
            {"number": 1, "correct_answer": [2, 3], "points": 2},
            {"number": 2, "correct_answer": 1, "points": 2},
        ]
    }
    assert handler.calculate_score_from_answers("국어-공통", answers) == 2

    converter = DataConverter(PathMapper(tmp_path), ModelNameMapper(tmp_path / "mapping.json"))
    exported = converter.excel_to_json("국어-공통", "모델", answers, handler)
    assert exported["model_scores"] == {"모델": 2}
    assert exported["results"][0]["correct_answer"] == [2, 3]
    assert exported["results"][0]["is_correct"] is True
    assert exported["results"][1]["answer_status"] == "no_answer"
    round_trip = converter.json_to_excel(exported)
    assert round_trip[0][1] == {1: 3, 2: None}
    assert round_trip[0][2] == 2


def test_legacy_update_formats_multiple_answer_statuses_and_syncs_official_answers(tmp_path: Path):
    """legacy 모델 열 갱신이 복수 정답 글꼴과 상태별 오류 표시를 유지한다."""
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "국어-공통"
    worksheet.append(["문항 번호", "정답", "모델"])
    worksheet.append([1, 9, 9])
    worksheet.append([2, 1, 9])
    worksheet.append([3, 2, 9])
    worksheet.append([4, 3, 9])
    worksheet.append(["총점", None, 0])
    excel_path = tmp_path / "legacy-update.xlsx"
    workbook.save(excel_path)

    handler = ExcelHandler(excel_path)
    source_questions = {
        "questions": [
            {"number": 1, "correct_answer": [2, 3], "points": 2},
            {"number": 2, "correct_answer": 1, "points": 2},
            {"number": 3, "correct_answer": 2, "points": 2},
            {"number": 4, "correct_answer": 3, "points": 2},
        ]
    }
    handler.update_correct_answer_cells("국어-공통", source_questions)
    handler.update_model_column(
        "국어-공통",
        "모델",
        {1: 3, 2: 4, 3: None, 4: "(검열)"},
        score=2,
    )

    updated = handler.workbook["국어-공통"]
    assert updated["B2"].value == "2, 3"
    assert updated["B3"].value == 1
    assert updated["C2"].font.color is None
    assert updated["C3"].font.color.rgb.endswith("FF0000")
    assert updated["C4"].value == "(포기)"
    assert updated["C4"].font.color.rgb.endswith("FF0000")
    assert updated["C5"].value == "(검열)"
    assert updated["C5"].font.color.rgb.endswith("7C3AED")
