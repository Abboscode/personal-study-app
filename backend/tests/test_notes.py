import asyncio
import json
from io import BytesIO
from pathlib import Path
from tempfile import SpooledTemporaryFile

import pytest
import httpx
from fastapi import UploadFile
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import delete_note, generate_notes, save_notes, update_note
from app.models import LectureSource, Note, Question, ReviewHistory, ReviewState, Subject
from app.schemas import NoteSaveRequest, NoteUpdate
from app.services.generation import ExtractedPdf
from app.services.lecture_sources import persist_lecture_source
from app.services.note_generation import (
    GeneratedNoteOutputError,
    compose_note_generation_prompt,
    generate_note_preview,
    note_generation_response_schema,
    validate_generated_note_sections,
)
from app.services.openrouter import generation_response_schema, request_openrouter


def note_document(note_type: str = "formula", source_page: int = 1) -> dict:
    note = {
        "formula": {
            "type": "formula",
            "title": "Formula Note",
            "purpose": "Quantization interval.",
            "formula": "\\[V_q=V_{FR}/2^{N_b}\\]",
            "variables": ["V_q = interval", "N_b = resolution in bits"],
            "example": "5 V / 256 is about 19.5 mV.",
        },
        "theorem": {
            "type": "theorem",
            "title": "Theorem Note",
            "meaning": "Sampling requirement.",
            "statement": "\\[f_s \\ge 2f_{max}\\]",
            "example": "3 kHz needs at least 6 kHz.",
        },
        "concept": {
            "type": "concept",
            "title": "Concept Note",
            "meaning": "A short concept.",
            "why_it_matters": "It guides design.",
        },
        "procedure": {
            "type": "procedure",
            "title": "Procedure Note",
            "purpose": "Configure the converter.",
            "steps": ["Select the range.", "Select the resolution."],
            "important_condition": None,
        },
    }[note_type]
    note["source_page"] = source_page
    return {
        "sections": [
            {
                "subject": "Testing and Certification",
                "section": "ADC Quantization",
                "notes": [note],
            }
        ]
    }


def pdf_bytes(text: str = "ADC quantization") -> bytes:
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


def upload(raw: bytes, filename: str = "lecture.pdf") -> UploadFile:
    temporary = SpooledTemporaryFile()
    temporary.write(raw)
    temporary.seek(0)
    return UploadFile(file=temporary, filename=filename)


@pytest.mark.parametrize("note_type", ["concept", "formula", "theorem", "procedure"])
def test_valid_typed_note_is_rendered_to_markdown(note_type: str) -> None:
    sections = validate_generated_note_sections(
        note_document(note_type),
        subject_name="Testing and Certification",
        page_count=2,
        requested_section=None,
    )
    assert sections[0].notes[0].type == note_type
    assert sections[0].notes[0].source_page == 1
    assert sections[0].notes[0].content_markdown.startswith("### ")


def test_concept_missing_meaning_is_rejected() -> None:
    document = note_document("concept")
    del document["sections"][0]["notes"][0]["meaning"]
    with pytest.raises(GeneratedNoteOutputError, match="meaning"):
        validate_generated_note_sections(
            document,
            subject_name="Testing and Certification",
            page_count=2,
            requested_section=None,
        )


def test_formula_missing_example_is_rejected() -> None:
    document = note_document("formula")
    del document["sections"][0]["notes"][0]["example"]
    with pytest.raises(GeneratedNoteOutputError, match="example"):
        validate_generated_note_sections(
            document,
            subject_name="Testing and Certification",
            page_count=2,
            requested_section=None,
        )


def test_typed_formula_is_converted_to_expected_markdown() -> None:
    note = validate_generated_note_sections(
        note_document("formula"),
        subject_name="Testing and Certification",
        page_count=2,
        requested_section=None,
    )[0].notes[0]
    assert note.content_markdown == (
        "### Purpose\n\nQuantization interval.\n\n"
        "### Formula\n\n\\[V_q=V_{FR}/2^{N_b}\\]\n\n"
        "### Variables\n\n- V_q = interval\n- N_b = resolution in bits\n\n"
        "### Simple Example\n\n5 V / 256 is about 19.5 mV."
    )


def test_source_page_is_validated_after_structured_conversion() -> None:
    with pytest.raises(GeneratedNoteOutputError, match="invalid source_page"):
        validate_generated_note_sections(
            note_document("formula", source_page=9),
            subject_name="Testing and Certification",
            page_count=2,
            requested_section=None,
        )


def test_note_schema_is_typed_and_question_schema_is_unchanged() -> None:
    note_schema = note_generation_response_schema()
    note_properties = note_schema["properties"]["sections"]["items"][
        "properties"
    ]["notes"]["items"]["properties"]
    assert {"meaning", "purpose", "formula", "statement", "steps"} <= set(
        note_properties
    )
    assert "$defs" not in note_schema
    assert "oneOf" not in str(note_schema)
    assert "content_markdown" not in str(note_schema)

    question_schema = generation_response_schema()
    question_section = question_schema["properties"]["sections"]["items"]
    assert "questions" in question_section["properties"]
    question_properties = question_section["properties"]["questions"]["items"][
        "properties"
    ]
    assert "external_id" in question_properties
    assert "meaning" not in question_properties
    assert "external_id" not in note_properties
    assert "questions" not in note_properties
    assert "content_markdown" not in str(question_schema)


def test_note_prompt_is_separate_and_keeps_stable_order() -> None:
    prompt, profile = compose_note_generation_prompt(
        subject_name="Testing and Certification",
        pdf_filename="adc.pdf",
        pdf_text="[PDF PAGE 1]\nADC",
        section_name=None,
    )
    assert profile == "testing_certification"
    assert "Create concise reference notes" in prompt
    assert "base_question_generation" not in prompt
    assert (
        prompt.index("# Role")
        < prompt.index("# Subject profile")
        < prompt.index("# Generation context")
        < prompt.index("# Extracted lecture content")
        < prompt.index("[PDF PAGE 1]")
    )


def test_note_preview_uses_note_schema_and_does_not_write(db: Session) -> None:
    async def provider(**kwargs):
        assert kwargs["schema_name"] == "study_note_sections"
        assert kwargs["operation_name"] == "notes"
        assert kwargs["allow_json_fallback"] is True
        assert kwargs["max_completion_tokens"] == 32000
        assert kwargs["response_schema"]["required"] == ["sections"]
        note_properties = kwargs["response_schema"]["properties"]["sections"][
            "items"
        ]["properties"]["notes"]["items"]["properties"]
        assert "meaning" in note_properties
        assert "external_id" not in note_properties
        return note_document("concept")

    sections, _ = asyncio.run(
        generate_note_preview(
            subject_name="Testing and Certification",
            pdf_filename="adc.pdf",
            extracted_pdf=ExtractedPdf(
                text="[PDF PAGE 1]\nADC", pages=1, characters=16, estimated_tokens=4
            ),
            section_name=None,
            model="test/model",
            api_key="test-key",
            provider_request=provider,
        )
    )
    assert sections[0].notes[0].source_page == 1
    assert db.scalar(select(func.count(Note.id))) == 0
    assert db.scalar(select(func.count(Question.id))) == 0


def test_note_request_falls_back_to_json_and_still_validates_locally() -> None:
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            assert body["response_format"]["type"] == "json_schema"
            return httpx.Response(
                400,
                json={"error": {"message": "Provider returned error"}},
            )
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(note_document("concept"))}}
                ]
            },
        )

    raw_output = asyncio.run(
        request_openrouter(
            prompt="Generate typed notes as JSON",
            model="test/model",
            api_key="secret",
            response_schema=note_generation_response_schema(),
            schema_name="study_note_sections",
            operation_name="notes",
            allow_json_fallback=True,
            transport=httpx.MockTransport(handler),
        )
    )
    sections = validate_generated_note_sections(
        raw_output,
        subject_name="Testing and Certification",
        page_count=1,
        requested_section=None,
    )
    assert len(requests) == 2
    assert sections[0].notes[0].content_markdown.startswith("### Meaning")


def test_existing_source_and_new_pdf_generation_reuse_document(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = Subject(name="Testing and Certification")
    db.add(subject)
    db.commit()
    db.refresh(subject)
    raw = pdf_bytes()
    monkeypatch.setenv("LECTURE_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    source = persist_lecture_source(
        db,
        subject=subject,
        original_filename="adc.pdf",
        raw=raw,
        page_count=1,
        storage_root=tmp_path,
    )

    async def fake_preview(**kwargs):
        return validate_generated_note_sections(
            note_document(),
            subject_name="Testing and Certification",
            page_count=1,
            requested_section=None,
        ), "testing_certification"

    monkeypatch.setattr("app.main.generate_note_preview", fake_preview)
    existing_preview = asyncio.run(
        generate_notes(
            subject_id=subject.id,
            source_document_id=source.id,
            file=None,
            section_mode="auto",
            section_name=None,
            model="test/model",
            db=db,
        )
    )
    uploaded_preview = asyncio.run(
        generate_notes(
            subject_id=subject.id,
            source_document_id=None,
            file=upload(raw, "same-adc.pdf"),
            section_mode="auto",
            section_name=None,
            model="test/model",
            db=db,
        )
    )
    assert existing_preview.source_document_id == source.id
    assert uploaded_preview.source_document_id == source.id
    assert db.scalar(select(func.count(LectureSource.id))) == 1
    assert db.scalar(select(func.count(Note.id))) == 0


def test_save_notes_preserves_source_page_skips_duplicates_and_never_creates_fsrs(
    db: Session, tmp_path: Path
) -> None:
    subject = Subject(name="Testing and Certification")
    db.add(subject)
    db.commit()
    db.refresh(subject)
    source = persist_lecture_source(
        db,
        subject=subject,
        original_filename="adc.pdf",
        raw=pdf_bytes(),
        page_count=1,
        storage_root=tmp_path,
    )
    section = validate_generated_note_sections(
        note_document(),
        subject_name="Testing and Certification",
        page_count=1,
        requested_section=None,
    )[0]
    payload = NoteSaveRequest(
        subject_id=subject.id,
        source_document_id=source.id,
        sections=[section],
    )

    first = save_notes(payload, db)
    second = save_notes(payload, db)

    assert first.saved == 1
    assert first.duplicates == 0
    assert second.saved == 0
    assert second.duplicates == 1
    note = db.scalar(select(Note))
    assert note is not None
    assert note.source_page == "1"
    assert note.source_document_id == source.id
    assert db.scalar(select(func.count(Note.id))) == 1
    assert db.scalar(select(func.count(Question.id))) == 0
    assert db.scalar(select(func.count(ReviewState.id))) == 0
    assert db.scalar(select(func.count(ReviewHistory.id))) == 0


def test_saved_note_can_be_edited_and_deleted(db: Session, tmp_path: Path) -> None:
    subject = Subject(name="Testing and Certification")
    db.add(subject)
    db.commit()
    db.refresh(subject)
    source = persist_lecture_source(
        db,
        subject=subject,
        original_filename="adc.pdf",
        raw=pdf_bytes(),
        page_count=1,
        storage_root=tmp_path,
    )
    save_notes(
        NoteSaveRequest(
            subject_id=subject.id,
            source_document_id=source.id,
            sections=[
                validate_generated_note_sections(
                    note_document(),
                    subject_name="Testing and Certification",
                    page_count=1,
                    requested_section=None,
                )[0]
            ],
        ),
        db,
    )
    note_id = db.scalar(select(Note.id))
    assert note_id is not None

    updated = update_note(
        note_id,
        NoteUpdate(title="Edited Formula Note", source_page="1"),
        db,
    )
    assert updated["title"] == "Edited Formula Note"
    assert updated["source_page"] == "1"

    delete_note(note_id, db)
    assert db.scalar(select(func.count(Note.id))) == 0
    assert db.scalar(select(func.count(ReviewState.id))) == 0
    assert db.scalar(select(func.count(ReviewHistory.id))) == 0
