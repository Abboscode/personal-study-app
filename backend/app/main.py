import json
import logging
import os
from datetime import datetime, time, timezone
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    LectureSource,
    Note,
    Question,
    ReviewHistory,
    ReviewState,
    Section,
    Subject,
    Tag,
)
from app.schemas import (
    BatchFileImportResult,
    BatchImportSummary,
    GenerationPreview,
    GeneratedNoteSection,
    ImportPayload,
    ImportSummary,
    NoteGenerationPreview,
    NoteSaveRequest,
    NoteSaveSummary,
    NoteUpdate,
    PdfEstimate,
    QuestionUpdate,
    RateRequest,
    RateResponse,
    SubjectCreate,
)
from app.services.generation import (
    GeneratedOutputError,
    GenerationConfigurationError,
    PdfExtractionError,
    extract_pdf_text,
    generate_preview,
)
from app.services.importer import import_questions
from app.services.lecture_sources import (
    LectureStorageError,
    persist_lecture_source,
    resolve_lecture_file,
)
from app.services.note_generation import (
    GeneratedNoteOutputError,
    generate_note_preview,
    validate_rendered_note_sections,
)
from app.services.scheduler import rate_question
from app.services.openrouter import (
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS,
    DEFAULT_OPENROUTER_MODEL,
    DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
    OpenRouterHTTPError,
    OpenRouterResponseError,
    OpenRouterTimeoutError,
)


logger = logging.getLogger("app.generation")
app = FastAPI(title="Personal Study API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 500_000
MAX_OPENROUTER_TIMEOUT_SECONDS = 900.0
MAX_OPENROUTER_COMPLETION_TOKENS = 128_000


def openrouter_timeout_seconds() -> float:
    raw_value = os.getenv("OPENROUTER_TIMEOUT_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_OPENROUTER_TIMEOUT_SECONDS
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise GenerationConfigurationError(
            "OPENROUTER_TIMEOUT_SECONDS must be a number"
        ) from exc
    if timeout <= 0 or timeout > MAX_OPENROUTER_TIMEOUT_SECONDS:
        raise GenerationConfigurationError(
            "OPENROUTER_TIMEOUT_SECONDS must be between 1 and 900"
        )
    return timeout


def openrouter_max_completion_tokens() -> int:
    raw_value = os.getenv("OPENROUTER_MAX_COMPLETION_TOKENS", "").strip()
    if not raw_value:
        return DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS
    try:
        max_tokens = int(raw_value)
    except ValueError as exc:
        raise GenerationConfigurationError(
            "OPENROUTER_MAX_COMPLETION_TOKENS must be an integer"
        ) from exc
    if max_tokens <= 0 or max_tokens > MAX_OPENROUTER_COMPLETION_TOKENS:
        raise GenerationConfigurationError(
            "OPENROUTER_MAX_COMPLETION_TOKENS must be between 1 and 128000"
        )
    return max_tokens


def generation_failure(
    *,
    status_code: int,
    error: str,
    message: str,
    stage: str,
    selected_model: str,
    exc: Exception,
) -> JSONResponse:
    provider_status = (
        exc.status_code if isinstance(exc, OpenRouterHTTPError) else None
    )
    provider_message = (
        exc.provider_message if isinstance(exc, OpenRouterHTTPError) else None
    )
    safe_message = " ".join(message.splitlines())[:1000]
    safe_provider_message = (
        " ".join(provider_message.splitlines())[:500]
        if provider_message
        else None
    )
    logger.error(
        "generation_failed stage=%s http_status=%s provider_message=%r "
        "model=%r structured_output=%s exception_type=%s message=%r",
        stage,
        provider_status,
        safe_provider_message,
        selected_model,
        True,
        type(exc).__name__,
        safe_message,
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "message": safe_message, "stage": stage},
    )


def question_dict(question: Question, include_answer: bool = True) -> dict:
    result = {
        "id": question.id,
        "external_id": question.external_id,
        "question_type": question.question_type,
        "question": question.question,
        "difficulty_level": question.difficulty_level,
        "source": question.source,
        "source_page": question.source_page,
        "tags": [tag.name for tag in question.tags],
        "section_id": question.section_id,
        "source_document": (
            {
                "id": question.source_document.id,
                "filename": question.source_document.original_filename,
            }
            if question.source_document is not None
            else None
        ),
    }
    if include_answer:
        result["answer"] = question.answer
    return result


def note_dict(note: Note) -> dict:
    return {
        "id": note.id,
        "subject_id": note.subject_id,
        "section_id": note.section_id,
        "section_name": note.section.name,
        "source_document_id": note.source_document_id,
        "source_document": (
            {
                "id": note.source_document.id,
                "filename": note.source_document.original_filename,
            }
            if note.source_document is not None
            else None
        ),
        "source_page": note.source_page,
        "note_type": note.note_type,
        "title": note.title,
        "content_markdown": note.content_markdown,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def normalized_note_title(title: str) -> str:
    return " ".join(title.casefold().split())


def note_duplicate_exists(
    db: Session,
    *,
    source_document_id: int | None,
    note_type: str,
    title: str,
    exclude_note_id: int | None = None,
) -> bool:
    statement = select(Note).where(
        Note.source_document_id == source_document_id,
        Note.note_type == note_type,
    )
    if exclude_note_id is not None:
        statement = statement.where(Note.id != exclude_note_id)
    normalized_title = normalized_note_title(title)
    return any(
        normalized_note_title(note.title) == normalized_title
        for note in db.scalars(statement)
    )


def is_due_at(due_at: datetime, now: datetime) -> bool:
    # PostgreSQL preserves timezone information; SQLite used by tests does not.
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    return due_at <= now


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ok"}


@app.get("/api/subjects")
def list_subjects(db: Session = Depends(get_db)) -> list[dict]:
    subjects = db.scalars(
        select(Subject).options(selectinload(Subject.sections)).order_by(Subject.name)
    ).all()
    result = []
    for subject in subjects:
        question_count = db.scalar(
            select(func.count(Question.id))
            .join(Section)
            .where(Section.subject_id == subject.id)
        )
        due_count = db.scalar(
            select(func.count(Question.id))
            .join(Section)
            .join(ReviewState)
            .where(
                Section.subject_id == subject.id,
                ReviewState.due_at <= datetime.now(timezone.utc),
            )
        )
        result.append(
            {
                "id": subject.id,
                "name": subject.name,
                "description": subject.description,
                "section_count": len(subject.sections),
                "question_count": question_count or 0,
                "due_count": due_count or 0,
                "note_count": db.scalar(
                    select(func.count(Note.id)).where(Note.subject_id == subject.id)
                )
                or 0,
            }
        )
    return result


@app.post("/api/subjects", status_code=201)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db)) -> dict:
    name = payload.name.strip()
    if db.scalar(select(Subject).where(Subject.name == name)):
        raise HTTPException(409, "A subject with this name already exists")
    subject = Subject(name=name, description=payload.description)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return {"id": subject.id, "name": subject.name, "description": subject.description}


@app.get("/api/subjects/{subject_id}")
def get_subject(subject_id: int, db: Session = Depends(get_db)) -> dict:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Subject not found")
    return {
        "id": subject.id,
        "name": subject.name,
        "description": subject.description,
        "note_count": db.scalar(
            select(func.count(Note.id)).where(Note.subject_id == subject.id)
        )
        or 0,
    }


@app.get("/api/subjects/{subject_id}/sections")
def list_sections(subject_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Subject, subject_id) is None:
        raise HTTPException(404, "Subject not found")
    sections = db.scalars(
        select(Section).where(Section.subject_id == subject_id).order_by(Section.name)
    ).all()
    return [
        {
            "id": section.id,
            "name": section.name,
            "description": section.description,
            "question_count": db.scalar(
                select(func.count(Question.id)).where(Question.section_id == section.id)
            )
            or 0,
            "due_count": db.scalar(
                select(func.count(Question.id))
                .join(ReviewState)
                .where(
                    Question.section_id == section.id,
                    ReviewState.due_at <= datetime.now(timezone.utc),
                )
            )
            or 0,
            "note_count": db.scalar(
                select(func.count(Note.id)).where(Note.section_id == section.id)
            )
            or 0,
        }
        for section in sections
    ]


def lecture_source_summary(source: LectureSource, db: Session) -> dict:
    return {
        "id": source.id,
        "subject_id": source.subject_id,
        "original_filename": source.original_filename,
        "page_count": source.page_count,
        "uploaded_at": source.uploaded_at,
        "question_count": db.scalar(
            select(func.count(Question.id)).where(
                Question.source_document_id == source.id
            )
        )
        or 0,
        "note_count": db.scalar(
            select(func.count(Note.id)).where(
                Note.source_document_id == source.id
            )
        )
        or 0,
        "section_count": db.scalar(
            select(func.count(func.distinct(Question.section_id))).where(
                Question.source_document_id == source.id
            )
        )
        or 0,
        "file_url": f"/api/lecture-sources/{source.id}/file",
    }


@app.get("/api/subjects/{subject_id}/lecture-sources")
def list_lecture_sources(
    subject_id: int, db: Session = Depends(get_db)
) -> list[dict]:
    if db.get(Subject, subject_id) is None:
        raise HTTPException(404, "Subject not found")
    sources = db.scalars(
        select(LectureSource)
        .where(LectureSource.subject_id == subject_id)
        .order_by(LectureSource.uploaded_at.desc(), LectureSource.id.desc())
    ).all()
    return [lecture_source_summary(source, db) for source in sources]


@app.get("/api/lecture-sources/{source_id}")
def get_lecture_source(source_id: int, db: Session = Depends(get_db)) -> dict:
    source = db.scalar(
        select(LectureSource)
        .where(LectureSource.id == source_id)
        .options(selectinload(LectureSource.subject))
    )
    if source is None:
        raise HTTPException(404, "Lecture source not found")
    sections = db.execute(
        select(Section.id, Section.name, func.count(Question.id))
        .join(Question, Question.section_id == Section.id)
        .where(Question.source_document_id == source.id)
        .group_by(Section.id, Section.name)
        .order_by(Section.name)
    ).all()
    note_sections = db.execute(
        select(Section.id, Section.name, func.count(Note.id))
        .join(Note, Note.section_id == Section.id)
        .where(Note.source_document_id == source.id)
        .group_by(Section.id, Section.name)
        .order_by(Section.name)
    ).all()
    return {
        **lecture_source_summary(source, db),
        "subject_name": source.subject.name,
        "sections": [
            {"id": row[0], "name": row[1], "question_count": row[2]}
            for row in sections
        ],
        "note_sections": [
            {"id": row[0], "name": row[1], "note_count": row[2]}
            for row in note_sections
        ],
    }


@app.get("/api/lecture-sources/{source_id}/file", response_class=FileResponse)
def get_lecture_source_file(
    source_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    source = db.get(LectureSource, source_id)
    if source is None:
        raise HTTPException(404, "Lecture source not found")
    try:
        file_path = resolve_lecture_file(source)
    except LectureStorageError as exc:
        raise HTTPException(404, "Lecture source file not found") from exc
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=source.original_filename,
        content_disposition_type="inline",
    )


def notes_for_statement(statement, db: Session) -> list[dict]:
    notes = db.scalars(
        statement.options(
            selectinload(Note.section), selectinload(Note.source_document)
        ).order_by(Section.name, Note.title)
    ).all()
    return [note_dict(note) for note in notes]


@app.get("/api/subjects/{subject_id}/notes")
def list_subject_notes(subject_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Subject, subject_id) is None:
        raise HTTPException(404, "Subject not found")
    return notes_for_statement(
        select(Note).join(Section).where(Note.subject_id == subject_id), db
    )


@app.get("/api/sections/{section_id}/notes")
def list_section_notes(section_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Section, section_id) is None:
        raise HTTPException(404, "Section not found")
    return notes_for_statement(
        select(Note).join(Section).where(Note.section_id == section_id), db
    )


@app.patch("/api/notes/{note_id}")
def update_note(
    note_id: int, payload: NoteUpdate, db: Session = Depends(get_db)
) -> dict:
    note = db.scalar(
        select(Note)
        .where(Note.id == note_id)
        .options(selectinload(Note.section), selectinload(Note.source_document))
    )
    if note is None:
        raise HTTPException(404, "Note not found")
    values = payload.model_dump(exclude_unset=True)
    prospective_type = values.get("note_type", note.note_type)
    prospective_title = values.get("title", note.title)
    if note_duplicate_exists(
        db,
        source_document_id=note.source_document_id,
        note_type=prospective_type,
        title=prospective_title,
        exclude_note_id=note.id,
    ):
        raise HTTPException(409, "A note with this source, type, and title exists")
    for key, value in values.items():
        if key == "source_page" and value is not None:
            value = str(value)
        setattr(note, key, value)
    db.commit()
    db.refresh(note)
    return note_dict(note)


@app.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db)) -> None:
    if db.get(Note, note_id) is None:
        raise HTTPException(404, "Note not found")
    db.execute(delete(Note).where(Note.id == note_id))
    db.commit()


@app.get("/api/sections/{section_id}")
def get_section(section_id: int, db: Session = Depends(get_db)) -> dict:
    section = db.scalar(
        select(Section)
        .where(Section.id == section_id)
        .options(selectinload(Section.subject))
    )
    if section is None:
        raise HTTPException(404, "Section not found")
    return {
        "id": section.id,
        "name": section.name,
        "description": section.description,
        "subject_id": section.subject_id,
        "subject_name": section.subject.name,
        "question_count": db.scalar(
            select(func.count(Question.id)).where(Question.section_id == section.id)
        )
        or 0,
        "due_count": db.scalar(
            select(func.count(Question.id))
            .join(ReviewState)
            .where(
                Question.section_id == section.id,
                ReviewState.due_at <= datetime.now(timezone.utc),
            )
        )
        or 0,
        "note_count": db.scalar(
            select(func.count(Note.id)).where(Note.section_id == section.id)
        )
        or 0,
    }


@app.get("/api/sections/{section_id}/questions")
def list_questions(section_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Section, section_id) is None:
        raise HTTPException(404, "Section not found")
    questions = db.scalars(
        select(Question)
        .where(Question.section_id == section_id)
        .options(
            selectinload(Question.tags),
            selectinload(Question.review_state),
            selectinload(Question.source_document),
        )
        .order_by(Question.id)
    ).all()
    now = datetime.now(timezone.utc)
    return [
        {
            **question_dict(question),
            "due_at": question.review_state.due_at,
            "is_due": is_due_at(question.review_state.due_at, now),
        }
        for question in questions
    ]


@app.get("/api/questions/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db)) -> dict:
    question = db.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(
            selectinload(Question.tags), selectinload(Question.source_document)
        )
    )
    if question is None:
        raise HTTPException(404, "Question not found")
    return question_dict(question)


@app.patch("/api/questions/{question_id}")
def update_question(
    question_id: int, payload: QuestionUpdate, db: Session = Depends(get_db)
) -> dict:
    question = db.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(
            selectinload(Question.tags), selectinload(Question.source_document)
        )
    )
    if question is None:
        raise HTTPException(404, "Question not found")
    values = payload.model_dump(exclude_unset=True)
    tag_names = values.pop("tags", None)
    for key, value in values.items():
        setattr(question, key, value)
    if tag_names is not None:
        clean_names = list(dict.fromkeys(name.strip().lower() for name in tag_names if name.strip()))
        existing = {
            tag.name: tag
            for tag in db.scalars(select(Tag).where(Tag.name.in_(clean_names)))
        }
        question.tags = [
            existing.get(name) or Tag(name=name) for name in clean_names
        ]
    db.commit()
    db.refresh(question)
    return question_dict(question)


@app.delete("/api/questions/{question_id}", status_code=204)
def delete_question(question_id: int, db: Session = Depends(get_db)) -> None:
    if db.get(Question, question_id) is None:
        raise HTTPException(404, "Question not found")
    db.execute(delete(Question).where(Question.id == question_id))
    db.commit()


@app.post("/api/import", response_model=ImportSummary)
async def import_json(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ImportSummary:
    if file.content_type not in {"application/json", "text/json", "text/plain"}:
        raise HTTPException(415, "Upload a JSON file")
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "JSON file must be 5 MB or smaller")
    try:
        document = json.loads(raw)
        payload = ImportPayload.model_validate(document)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(422, f"Invalid JSON: {exc}") from exc
    except ValidationError as exc:
        raise HTTPException(422, detail=json.loads(exc.json(include_url=False))) from exc
    try:
        return import_questions(db, payload, file.filename or "upload.json")
    except Exception:
        db.rollback()
        raise


def validation_error_messages(exc: ValidationError) -> list[str]:
    messages = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error["loc"])
        messages.append(f"{location}: {error['msg']}" if location else error["msg"])
    return messages


async def read_pdf(file: UploadFile):
    filename = file.filename or "lecture.pdf"
    if not filename.casefold().endswith(".pdf"):
        raise HTTPException(415, "Upload a PDF file")
    raw = await file.read(MAX_PDF_BYTES + 1)
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF file must be 25 MB or smaller")
    try:
        extracted = extract_pdf_text(raw)
    except PdfExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc
    if extracted.characters > MAX_EXTRACTED_CHARACTERS:
        raise HTTPException(
            413,
            "Extracted PDF text is too large; split the lecture into smaller PDFs",
        )
    return filename, raw, extracted


@app.get("/api/generate/config")
def generation_config() -> dict:
    model = os.getenv("OPENROUTER_MODEL", "").strip() or DEFAULT_OPENROUTER_MODEL
    return {
        "provider": "openrouter",
        "default_model": model,
        "api_key_configured": bool(os.getenv("OPENROUTER_API_KEY", "").strip()),
    }


@app.post("/api/generate/estimate", response_model=PdfEstimate)
async def estimate_generation_pdf(file: UploadFile = File(...)) -> PdfEstimate:
    filename, _, extracted = await read_pdf(file)
    return PdfEstimate(
        filename=filename,
        pages=extracted.pages,
        extracted_characters=extracted.characters,
        estimated_input_tokens=extracted.estimated_tokens,
    )


@app.post("/api/generation", response_model=GenerationPreview)
async def generate_questions(
    subject_id: int = Form(...),
    file: UploadFile = File(...),
    section_mode: Literal["auto", "manual"] = Form("auto"),
    section_name: str | None = Form(None),
    model: str | None = Form(None),
    db: Session = Depends(get_db),
) -> GenerationPreview | JSONResponse:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Subject not found")
    selected_section = None if section_mode == "auto" else (section_name or "").strip()
    if section_mode == "manual" and not selected_section:
        raise HTTPException(422, "Enter a section name or use automatic detection")

    selected_model = (
        model or os.getenv("OPENROUTER_MODEL", "") or DEFAULT_OPENROUTER_MODEL
    ).strip()
    base_url = (
        os.getenv("OPENROUTER_BASE_URL", "").strip()
        or DEFAULT_OPENROUTER_BASE_URL
    )
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        exc = GenerationConfigurationError(
            "OPENROUTER_API_KEY is not configured on the backend"
        )
        return generation_failure(
            status_code=503,
            error="generation_configuration_error",
            message=str(exc),
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )
    try:
        timeout_seconds = openrouter_timeout_seconds()
        max_completion_tokens = openrouter_max_completion_tokens()
    except GenerationConfigurationError as exc:
        return generation_failure(
            status_code=503,
            error="generation_configuration_error",
            message=str(exc),
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )

    try:
        filename, raw, extracted = await read_pdf(file)
    except HTTPException as exc:
        return generation_failure(
            status_code=exc.status_code,
            error="pdf_extraction_error",
            message=str(exc.detail),
            stage="pdf_extraction",
            selected_model=selected_model,
            exc=exc,
        )
    try:
        source_document = persist_lecture_source(
            db,
            subject=subject,
            original_filename=filename,
            raw=raw,
            page_count=extracted.pages,
        )
    except LectureStorageError as exc:
        db.rollback()
        return generation_failure(
            status_code=500,
            error="pdf_storage_error",
            message=str(exc),
            stage="pdf_storage",
            selected_model=selected_model,
            exc=exc,
        )
    try:
        sections, profile = await generate_preview(
            subject_name=subject.name,
            pdf_filename=filename,
            extracted_pdf=extracted,
            section_name=selected_section,
            model=selected_model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_completion_tokens=max_completion_tokens,
        )
    except GenerationConfigurationError as exc:
        return generation_failure(
            status_code=503,
            error="prompt_composition_error",
            message=str(exc),
            stage="prompt_composition",
            selected_model=selected_model,
            exc=exc,
        )
    except OpenRouterTimeoutError as exc:
        return generation_failure(
            status_code=504,
            error="openrouter_timeout",
            message=(
                f"OpenRouter did not respond within {timeout_seconds:g} seconds."
            ),
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )
    except OpenRouterHTTPError as exc:
        return generation_failure(
            status_code=502,
            error="openrouter_provider_error",
            message=str(exc),
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )
    except OpenRouterResponseError as exc:
        return generation_failure(
            status_code=502,
            error="openrouter_response_error",
            message=str(exc),
            stage="response_parsing",
            selected_model=selected_model,
            exc=exc,
        )
    except GeneratedOutputError as exc:
        return generation_failure(
            status_code=422,
            error="generated_schema_invalid",
            message=str(exc),
            stage="schema_validation",
            selected_model=selected_model,
            exc=exc,
        )

    try:
        return GenerationPreview(
            model=selected_model,
            profile=profile,
            source=filename,
            pages=extracted.pages,
            extracted_characters=extracted.characters,
            estimated_input_tokens=extracted.estimated_tokens,
            source_document_id=source_document.id,
            sections=sections,
        )
    except ValidationError as exc:
        return generation_failure(
            status_code=500,
            error="preview_creation_error",
            message="The validated generation could not be prepared for preview.",
            stage="preview_creation",
            selected_model=selected_model,
            exc=exc,
        )


@app.post("/api/notes/generation", response_model=NoteGenerationPreview)
async def generate_notes(
    subject_id: int = Form(...),
    source_document_id: Annotated[int | None, Form()] = None,
    file: UploadFile | None = File(None),
    section_mode: Literal["auto", "manual"] = Form("auto"),
    section_name: str | None = Form(None),
    model: str | None = Form(None),
    db: Session = Depends(get_db),
) -> NoteGenerationPreview | JSONResponse:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Subject not found")
    if (source_document_id is None) == (file is None):
        raise HTTPException(422, "Choose one existing lecture or upload one PDF")
    selected_section = None if section_mode == "auto" else (section_name or "").strip()
    if section_mode == "manual" and not selected_section:
        raise HTTPException(422, "Enter a section name or use automatic detection")

    selected_model = (
        model or os.getenv("OPENROUTER_MODEL", "") or DEFAULT_OPENROUTER_MODEL
    ).strip()
    base_url = (
        os.getenv("OPENROUTER_BASE_URL", "").strip()
        or DEFAULT_OPENROUTER_BASE_URL
    )
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        exc = GenerationConfigurationError(
            "OPENROUTER_API_KEY is not configured on the backend"
        )
        return generation_failure(
            status_code=503,
            error="generation_configuration_error",
            message=str(exc),
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )
    try:
        timeout_seconds = openrouter_timeout_seconds()
        max_completion_tokens = openrouter_max_completion_tokens()
    except GenerationConfigurationError as exc:
        return generation_failure(
            status_code=503,
            error="generation_configuration_error",
            message=str(exc),
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )

    if source_document_id is not None:
        source_document = db.get(LectureSource, source_document_id)
        if source_document is None or source_document.subject_id != subject.id:
            raise HTTPException(404, "Lecture source not found for this subject")
        try:
            raw = resolve_lecture_file(source_document).read_bytes()
        except (LectureStorageError, OSError) as exc:
            return generation_failure(
                status_code=500,
                error="pdf_storage_error",
                message="The stored lecture PDF could not be read.",
                stage="pdf_storage",
                selected_model=selected_model,
                exc=exc,
            )
        filename = source_document.original_filename
        try:
            extracted = extract_pdf_text(raw)
        except PdfExtractionError as exc:
            return generation_failure(
                status_code=422,
                error="pdf_extraction_error",
                message=str(exc),
                stage="pdf_extraction",
                selected_model=selected_model,
                exc=exc,
            )
    else:
        assert file is not None
        try:
            filename, raw, extracted = await read_pdf(file)
        except HTTPException as exc:
            return generation_failure(
                status_code=exc.status_code,
                error="pdf_extraction_error",
                message=str(exc.detail),
                stage="pdf_extraction",
                selected_model=selected_model,
                exc=exc,
            )
        try:
            source_document = persist_lecture_source(
                db,
                subject=subject,
                original_filename=filename,
                raw=raw,
                page_count=extracted.pages,
            )
        except LectureStorageError as exc:
            db.rollback()
            return generation_failure(
                status_code=500,
                error="pdf_storage_error",
                message=str(exc),
                stage="pdf_storage",
                selected_model=selected_model,
                exc=exc,
            )

    try:
        sections, profile = await generate_note_preview(
            subject_name=subject.name,
            pdf_filename=filename,
            extracted_pdf=extracted,
            section_name=selected_section,
            model=selected_model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_completion_tokens=max_completion_tokens,
        )
    except GenerationConfigurationError as exc:
        return generation_failure(
            status_code=503,
            error="prompt_composition_error",
            message=str(exc),
            stage="prompt_composition",
            selected_model=selected_model,
            exc=exc,
        )
    except OpenRouterTimeoutError as exc:
        return generation_failure(
            status_code=504,
            error="openrouter_timeout",
            message=f"OpenRouter did not respond within {timeout_seconds:g} seconds.",
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )
    except OpenRouterHTTPError as exc:
        return generation_failure(
            status_code=502,
            error="openrouter_provider_error",
            message=str(exc),
            stage="openrouter_request",
            selected_model=selected_model,
            exc=exc,
        )
    except OpenRouterResponseError as exc:
        return generation_failure(
            status_code=502,
            error="openrouter_response_error",
            message=str(exc),
            stage="response_parsing",
            selected_model=selected_model,
            exc=exc,
        )
    except GeneratedNoteOutputError as exc:
        return generation_failure(
            status_code=422,
            error="generated_schema_invalid",
            message=str(exc),
            stage="schema_validation",
            selected_model=selected_model,
            exc=exc,
        )

    for section in sections:
        for note in section.notes:
            note.duplicate = note_duplicate_exists(
                db,
                source_document_id=source_document.id,
                note_type=note.type,
                title=note.title,
            )
    return NoteGenerationPreview(
        model=selected_model,
        profile=profile,
        source=filename,
        pages=extracted.pages,
        extracted_characters=extracted.characters,
        estimated_input_tokens=extracted.estimated_tokens,
        source_document_id=source_document.id,
        sections=sections,
    )


@app.post("/api/notes", response_model=NoteSaveSummary)
def save_notes(payload: NoteSaveRequest, db: Session = Depends(get_db)) -> NoteSaveSummary:
    subject = db.get(Subject, payload.subject_id)
    if subject is None:
        raise HTTPException(404, "Subject not found")
    source_document = None
    page_count = 2_147_483_647
    if payload.source_document_id is not None:
        source_document = db.get(LectureSource, payload.source_document_id)
        if source_document is None or source_document.subject_id != subject.id:
            raise HTTPException(404, "Lecture source not found for this subject")
        page_count = source_document.page_count or page_count

    try:
        sections = validate_rendered_note_sections(
            payload.sections,
            subject_name=subject.name,
            page_count=page_count,
            requested_section=None,
        )
    except GeneratedNoteOutputError as exc:
        raise HTTPException(422, str(exc)) from exc

    received = sum(len(section.notes) for section in sections)
    saved = 0
    duplicates = 0
    section_ids: list[int] = []
    for generated_section in sections:
        section = db.scalar(
            select(Section).where(
                Section.subject_id == subject.id,
                Section.name == generated_section.section,
            )
        )
        for generated_note in generated_section.notes:
            if note_duplicate_exists(
                db,
                source_document_id=payload.source_document_id,
                note_type=generated_note.type,
                title=generated_note.title,
            ):
                duplicates += 1
                continue
            if section is None:
                section = Section(
                    subject_id=subject.id, name=generated_section.section
                )
                db.add(section)
                db.flush()
            db.add(
                Note(
                    subject_id=subject.id,
                    section_id=section.id,
                    source_document_id=payload.source_document_id,
                    source_page=(
                        str(generated_note.source_page)
                        if generated_note.source_page is not None
                        else None
                    ),
                    note_type=generated_note.type,
                    title=generated_note.title,
                    content_markdown=generated_note.content_markdown,
                )
            )
            db.flush()
            saved += 1
        if section is not None and section.id not in section_ids:
            section_ids.append(section.id)
    db.commit()
    return NoteSaveSummary(
        received=received,
        saved=saved,
        duplicates=duplicates,
        section_ids=section_ids,
    )


@app.post("/api/import/batch", response_model=BatchImportSummary)
async def import_json_batch(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    source_document_id: Annotated[int | None, Form()] = None,
) -> BatchImportSummary:
    source_document = None
    if source_document_id is not None:
        source_document = db.get(LectureSource, source_document_id)
        if source_document is None:
            raise HTTPException(404, "Lecture source not found")
    json_files = [
        file for file in files if (file.filename or "").lower().endswith(".json")
    ]
    results: list[BatchFileImportResult] = []
    questions_received = 0
    questions_imported = 0
    duplicates = 0
    error_count = 0

    for file in json_files:
        filename = file.filename or "upload.json"
        received = 0
        try:
            raw = await file.read(5 * 1024 * 1024 + 1)
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError("JSON file must be 5 MB or smaller")
            document = json.loads(raw)
            payload = ImportPayload.model_validate(document)
            received = len(payload.questions)
            questions_received += received

            summary = import_questions(
                db, payload, filename, source_document=source_document
            )
            questions_imported += summary.imported
            duplicates += summary.duplicates
            results.append(
                BatchFileImportResult(
                    filename=filename,
                    received=summary.received,
                    imported=summary.imported,
                    duplicates=summary.duplicates,
                )
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            db.rollback()
            error_count += 1
            results.append(
                BatchFileImportResult(
                    filename=filename,
                    received=received,
                    errors=[f"Invalid JSON: {exc}"],
                )
            )
        except ValidationError as exc:
            db.rollback()
            errors = validation_error_messages(exc)
            error_count += len(errors)
            results.append(
                BatchFileImportResult(
                    filename=filename,
                    received=received,
                    errors=errors,
                )
            )
        except ValueError as exc:
            db.rollback()
            error_count += 1
            results.append(
                BatchFileImportResult(
                    filename=filename,
                    received=received,
                    errors=[str(exc)],
                )
            )
        except Exception:
            db.rollback()
            error_count += 1
            results.append(
                BatchFileImportResult(
                    filename=filename,
                    received=received,
                    errors=["Import failed due to an internal error"],
                )
            )

    return BatchImportSummary(
        files_received=len(json_files),
        files_processed=len(results),
        questions_received=questions_received,
        questions_imported=questions_imported,
        duplicates=duplicates,
        errors=error_count,
        files=results,
    )


@app.get("/api/review/due")
def due_questions(
    limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)
) -> list[dict]:
    questions = db.scalars(
        select(Question)
        .join(ReviewState)
        .where(ReviewState.due_at <= datetime.now(timezone.utc))
        .options(
            selectinload(Question.tags),
            selectinload(Question.section).selectinload(Section.subject),
            selectinload(Question.review_state),
            selectinload(Question.source_document),
        )
        .order_by(ReviewState.due_at, Question.id)
        .limit(limit)
    ).all()
    return [
        {
            **question_dict(question),
            "subject": question.section.subject.name,
            "section": question.section.name,
            "due_at": question.review_state.due_at,
        }
        for question in questions
    ]


@app.post("/api/review/{question_id}/rate", response_model=RateResponse)
def rate(
    question_id: int, payload: RateRequest, db: Session = Depends(get_db)
) -> RateResponse:
    response = rate_question(db, question_id, payload.rating)
    if response is None:
        raise HTTPException(404, "Question or review state not found")
    return response


@app.get("/api/questions/{question_id}/history")
def review_history(question_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Question, question_id) is None:
        raise HTTPException(404, "Question not found")
    rows = db.scalars(
        select(ReviewHistory)
        .where(ReviewHistory.question_id == question_id)
        .order_by(ReviewHistory.reviewed_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "rating": row.rating,
            "reviewed_at": row.reviewed_at,
            "previous_due_at": row.previous_due_at,
            "next_due_at": row.next_due_at,
        }
        for row in rows
    ]


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    due_count = db.scalar(
        select(func.count(ReviewState.id)).where(ReviewState.due_at <= now)
    ) or 0
    new_count = db.scalar(
        select(func.count(ReviewState.id)).where(ReviewState.reps == 0)
    ) or 0
    reviewed_today = db.scalar(
        select(func.count(ReviewHistory.id)).where(
            ReviewHistory.reviewed_at >= today_start
        )
    ) or 0

    subjects = list_subjects(db)
    return {
        "due_today": due_count,
        "new_questions": new_count,
        "reviewed_today": reviewed_today,
        "subjects": subjects,
    }
