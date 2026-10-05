import asyncio
import json
from datetime import datetime, timedelta, timezone
from tempfile import SpooledTemporaryFile

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import (
    create_subject,
    dashboard,
    delete_question,
    get_section,
    import_json_batch,
    due_questions,
    health,
    list_questions,
    list_sections,
    update_question,
)
from app.models import Question, ReviewHistory, ReviewState, Section, Subject
from app.schemas import ImportPayload, QuestionUpdate, SubjectCreate
from app.services.importer import import_questions
from app.services.scheduler import rate_question


def do_import(db: Session, payload: dict):
    return import_questions(db, ImportPayload.model_validate(payload), "questions.json")


def upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(file=file, filename=filename)


def test_health_check(db: Session) -> None:
    assert health(db) == {"status": "ok"}


def test_subject_creation_and_duplicate_protection(db: Session) -> None:
    created = create_subject(SubjectCreate(name="SystemC"), db)
    assert created["name"] == "SystemC"
    with pytest.raises(HTTPException) as error:
        create_subject(SubjectCreate(name="SystemC"), db)
    assert error.value.status_code == 409


def test_import_creates_subject_section_question_and_state(
    db: Session, sample_payload: dict
) -> None:
    response = do_import(db, sample_payload)
    assert response.model_dump() == {
        "batch_id": 1,
        "received": 1,
        "imported": 1,
        "duplicates": 0,
        "errors": 0,
        "subject_id": 1,
        "section_id": 1,
    }
    subject = db.scalar(select(Subject))
    section = db.scalar(select(Section))
    assert subject is not None
    assert section is not None
    assert subject.name == "Electronics for Embedded Systems"
    assert section.name == "Memory Fundamentals, Organization & Interface"
    question = db.scalar(select(Question))
    assert question is not None
    assert {tag.name for tag in question.tags} == {
        "memory", "memory-organization", "addressing", "capacity"
    }
    assert question.review_state is not None
    assert question.review_state.reps == 0

    sections = list_sections(subject.id, db)
    assert sections == [
        {
            "id": section.id,
            "name": "Memory Fundamentals, Organization & Interface",
            "description": None,
            "question_count": 1,
            "due_count": 1,
        }
    ]
    section_detail = get_section(section.id, db)
    assert section_detail["subject_name"] == "Electronics for Embedded Systems"
    assert section_detail["question_count"] == 1
    assert section_detail["due_count"] == 1
    questions = list_questions(section.id, db)
    assert questions[0]["external_id"] == "efes-memories-001"
    assert questions[0]["is_due"] is True


def test_import_same_file_twice_is_idempotent(
    db: Session, sample_payload: dict
) -> None:
    assert do_import(db, sample_payload).imported == 1
    result = do_import(db, sample_payload)
    assert result.imported == 0
    assert result.duplicates == 1
    assert db.scalar(select(func.count(Question.id))) == 1


def test_import_ten_questions_then_reports_ten_duplicates(
    db: Session, sample_payload: dict
) -> None:
    base = sample_payload["questions"][0]
    sample_payload["questions"] = [
        {**base, "external_id": f"question-{index:02}"} for index in range(10)
    ]
    assert do_import(db, sample_payload).imported == 10
    result = do_import(db, sample_payload)
    assert result.imported == 0
    assert result.duplicates == 10
    assert db.scalar(select(func.count(Question.id))) == 10


def test_batch_import_continues_after_malformed_file_and_ignores_non_json(
    db: Session, sample_payload: dict
) -> None:
    valid_json = json.dumps(sample_payload).encode()
    result = asyncio.run(
        import_json_batch(
            files=[
                upload_file("memory.json", valid_json),
                upload_file("broken.json", b"{not valid json"),
                upload_file("memory-copy.json", valid_json),
                upload_file("notes.txt", b"not an import"),
            ],
            db=db,
        )
    )

    assert result.files_received == 3
    assert result.files_processed == 3
    assert result.questions_received == 2
    assert result.questions_imported == 1
    assert result.duplicates == 1
    assert result.errors == 1
    assert [item.filename for item in result.files] == [
        "memory.json",
        "broken.json",
        "memory-copy.json",
    ]
    assert result.files[1].errors
    assert result.files[2].duplicates == 1
    assert db.scalar(select(func.count(Question.id))) == 1


def test_full_document_is_validated_before_writes(
    db: Session, sample_payload: dict
) -> None:
    sample_payload["questions"][0]["type"] = "essay"
    with pytest.raises(ValidationError):
        ImportPayload.model_validate(sample_payload)
    assert db.scalar(select(func.count(Subject.id))) == 0


def test_question_edit_and_delete(
    db: Session, sample_payload: dict
) -> None:
    do_import(db, sample_payload)
    question_id = db.scalar(select(Question.id))
    response = update_question(
        question_id,
        QuestionUpdate(question="Updated question", difficulty_level=3, tags=["updated"]),
        db,
    )
    assert response["question"] == "Updated question"
    assert response["tags"] == ["updated"]
    delete_question(question_id, db)
    assert db.get(Question, question_id) is None
    assert db.scalar(select(func.count(ReviewState.id))) == 0


def test_due_question_and_good_rating_create_history_and_update_state(
    db: Session, sample_payload: dict
) -> None:
    do_import(db, sample_payload)
    question = db.scalar(select(Question))
    assert question is not None
    previous_due = question.review_state.due_at

    due = due_questions(limit=50, db=db)
    assert len(due) == 1
    assert due[0]["subject"] == "Electronics for Embedded Systems"
    assert due[0]["answer"]

    response = rate_question(db, question.id, "good")
    assert response is not None
    db.refresh(question.review_state)
    assert question.review_state.reps == 1
    stored_due = question.review_state.due_at
    if stored_due.tzinfo is None:  # SQLite drops timezone information.
        stored_due = stored_due.replace(tzinfo=timezone.utc)
    assert stored_due > previous_due
    assert db.scalar(select(func.count(ReviewHistory.id))) == 1
    history = db.scalar(select(ReviewHistory))
    assert history is not None
    assert history.rating == "good"
    assert history.next_due_at == question.review_state.due_at


def test_future_question_is_not_due(db: Session, sample_payload: dict) -> None:
    do_import(db, sample_payload)
    state = db.scalar(select(ReviewState))
    assert state is not None
    state.due_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.commit()
    assert due_questions(limit=50, db=db) == []


def test_dashboard_counts_review(db: Session, sample_payload: dict) -> None:
    do_import(db, sample_payload)
    question_id = db.scalar(select(Question.id))
    before = dashboard(db)
    assert before["due_today"] == 1
    assert before["new_questions"] == 1
    assert before["reviewed_today"] == 0
    rate_question(db, question_id, "easy")
    after = dashboard(db)
    assert after["new_questions"] == 0
    assert after["reviewed_today"] == 1
