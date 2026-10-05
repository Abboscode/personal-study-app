import json
import os
from datetime import datetime, time, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Question, ReviewHistory, ReviewState, Section, Subject, Tag
from app.schemas import (
    BatchFileImportResult,
    BatchImportSummary,
    ImportPayload,
    ImportSummary,
    QuestionUpdate,
    RateRequest,
    RateResponse,
    SubjectCreate,
)
from app.services.importer import import_questions
from app.services.scheduler import rate_question


app = FastAPI(title="Personal Study API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
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
    }
    if include_answer:
        result["answer"] = question.answer
    return result


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
    return {"id": subject.id, "name": subject.name, "description": subject.description}


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
        }
        for section in sections
    ]


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
    }


@app.get("/api/sections/{section_id}/questions")
def list_questions(section_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Section, section_id) is None:
        raise HTTPException(404, "Section not found")
    questions = db.scalars(
        select(Question)
        .where(Question.section_id == section_id)
        .options(selectinload(Question.tags), selectinload(Question.review_state))
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
        .options(selectinload(Question.tags))
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
        .options(selectinload(Question.tags))
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


@app.post("/api/import/batch", response_model=BatchImportSummary)
async def import_json_batch(
    files: list[UploadFile] = File(...), db: Session = Depends(get_db)
) -> BatchImportSummary:
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

            summary = import_questions(db, payload, filename)
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
