import asyncio
import json
import logging
from io import BytesIO
from pathlib import Path
from tempfile import SpooledTemporaryFile

import pytest
from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import (
    generate_questions,
    get_lecture_source,
    get_lecture_source_file,
    import_json_batch,
    list_lecture_sources,
)
from app.models import LectureSource, Question, Subject
from app.schemas import ImportPayload
from app.services.importer import import_questions
from app.services.lecture_sources import (
    lecture_storage_root,
    persist_lecture_source,
    resolve_lecture_file,
)
from app.services.openrouter import OpenRouterHTTPError


def pdf_bytes(text: str = "Lecture content") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def upload_file(raw: bytes, filename: str = "lecture.pdf") -> UploadFile:
    temporary = SpooledTemporaryFile()
    temporary.write(raw)
    temporary.seek(0)
    return UploadFile(file=temporary, filename=filename)


def add_subject(db: Session) -> Subject:
    subject = Subject(name="Electronics for Embedded Systems")
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


def test_generation_persists_pdf_and_metadata_without_inserting_questions(
    db: Session,
    sample_payload: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = add_subject(db)
    raw = pdf_bytes("Memory timing")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "47")
    monkeypatch.setenv("OPENROUTER_MAX_COMPLETION_TOKENS", "48000")
    monkeypatch.setenv("LECTURE_STORAGE_PATH", str(tmp_path))

    async def fake_generate_preview(**kwargs):
        assert kwargs["timeout_seconds"] == 47
        assert kwargs["max_completion_tokens"] == 48000
        assert kwargs["model"] == "test/model"
        return [ImportPayload.model_validate(sample_payload)], "electronics_embedded"

    monkeypatch.setattr("app.main.generate_preview", fake_generate_preview)
    preview = asyncio.run(
        generate_questions(
            subject_id=subject.id,
            file=upload_file(raw, "../Memory Timing.pdf"),
            section_mode="auto",
            section_name=None,
            model="test/model",
            db=db,
        )
    )

    source = db.get(LectureSource, preview.source_document_id)
    assert source is not None
    assert source.original_filename == "Memory Timing.pdf"
    assert source.page_count == 1
    assert source.file_hash
    assert resolve_lecture_file(source, tmp_path).read_bytes() == raw
    assert db.scalar(select(func.count(Question.id))) == 0


def test_generation_provider_failure_returns_structured_safe_error_and_logs_stage(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    subject = add_subject(db)
    monkeypatch.setenv("OPENROUTER_API_KEY", "never-log-this-key")
    monkeypatch.setenv("LECTURE_STORAGE_PATH", str(tmp_path))

    async def fake_generate_preview(**kwargs):
        raise OpenRouterHTTPError(
            "OpenRouter returned HTTP 400: structured output rejected",
            status_code=400,
            provider_message="structured output rejected",
        )

    monkeypatch.setattr("app.main.generate_preview", fake_generate_preview)
    with caplog.at_level(logging.ERROR, logger="app.generation"):
        response = asyncio.run(
            generate_questions(
                subject_id=subject.id,
                file=upload_file(pdf_bytes("Memory timing")),
                section_mode="auto",
                section_name=None,
                model="test/model",
                db=db,
            )
        )

    assert response.status_code == 502
    assert json.loads(response.body) == {
        "error": "openrouter_provider_error",
        "message": "OpenRouter returned HTTP 400: structured output rejected",
        "stage": "openrouter_request",
    }
    assert "stage=openrouter_request" in caplog.text
    assert "http_status=400" in caplog.text
    assert "model='test/model'" in caplog.text
    assert "structured_output=True" in caplog.text
    assert "exception_type=OpenRouterHTTPError" in caplog.text
    assert "never-log-this-key" not in caplog.text


def test_same_pdf_hash_reuses_source_metadata_and_file(
    db: Session, tmp_path: Path
) -> None:
    subject = add_subject(db)
    raw = pdf_bytes()
    first = persist_lecture_source(
        db,
        subject=subject,
        original_filename="lecture.pdf",
        raw=raw,
        page_count=1,
        storage_root=tmp_path,
    )
    second = persist_lecture_source(
        db,
        subject=subject,
        original_filename="renamed.pdf",
        raw=raw,
        page_count=1,
        storage_root=tmp_path,
    )

    assert second.id == first.id
    assert db.scalar(select(func.count(LectureSource.id))) == 1
    assert len(list(tmp_path.rglob("*.pdf"))) == 1


def test_approved_import_links_question_and_preserves_source_page(
    db: Session, sample_payload: dict, tmp_path: Path
) -> None:
    subject = add_subject(db)
    sample_payload["questions"][0]["source_page"] = 12
    source = persist_lecture_source(
        db,
        subject=subject,
        original_filename="memories.pdf",
        raw=pdf_bytes(),
        page_count=10,
        storage_root=tmp_path,
    )

    result = asyncio.run(
        import_json_batch(
            files=[upload_file(json.dumps(sample_payload).encode(), "generated.json")],
            db=db,
            source_document_id=source.id,
        )
    )
    assert result.questions_imported == 1
    question = db.scalar(select(Question))
    assert question is not None
    assert question.source_document_id == source.id
    assert question.source_page == "12"
    summaries = list_lecture_sources(subject.id, db)
    assert summaries[0]["question_count"] == 1
    assert summaries[0]["section_count"] == 1
    detail = get_lecture_source(source.id, db)
    assert detail["sections"][0]["question_count"] == 1


def test_manual_import_without_lecture_source_remains_valid(
    db: Session, sample_payload: dict
) -> None:
    import_questions(
        db, ImportPayload.model_validate(sample_payload), "manual-import.json"
    )
    question = db.scalar(select(Question))
    assert question is not None
    assert question.source == sample_payload["source"]
    assert question.source_document_id is None


def test_source_file_endpoint_requires_registered_safe_source(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = add_subject(db)
    monkeypatch.setenv("LECTURE_STORAGE_PATH", str(tmp_path))
    source = persist_lecture_source(
        db,
        subject=subject,
        original_filename="lecture.pdf",
        raw=pdf_bytes(),
        page_count=1,
        storage_root=tmp_path,
    )
    response = get_lecture_source_file(source.id, db)
    assert Path(response.path).read_bytes() == resolve_lecture_file(source).read_bytes()

    with pytest.raises(HTTPException) as missing:
        get_lecture_source_file(99999, db)
    assert missing.value.status_code == 404

    source.file_path = "../../etc/passwd"
    db.commit()
    with pytest.raises(HTTPException) as unsafe:
        get_lecture_source_file(source.id, db)
    assert unsafe.value.status_code == 404


def test_storage_path_is_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "persistent-lectures"
    monkeypatch.setenv("LECTURE_STORAGE_PATH", str(configured))
    assert lecture_storage_root() == configured
