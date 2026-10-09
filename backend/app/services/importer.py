from datetime import datetime, timezone

from fsrs import Card
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ImportBatch,
    LectureSource,
    Question,
    ReviewState,
    Section,
    Subject,
    Tag,
)
from app.schemas import ImportPayload, ImportSummary


def _new_review_state() -> ReviewState:
    card = Card()
    return ReviewState(
        due_at=card.due,
        state=card.state.name.lower(),
        stability=card.stability,
        fsrs_difficulty=card.difficulty,
        scheduled_days=0,
        elapsed_days=0,
        reps=0,
        lapses=0,
        last_review_at=card.last_review,
        card_json=card.to_json(),
    )


def import_questions(
    db: Session,
    payload: ImportPayload,
    filename: str,
    source_document: LectureSource | None = None,
) -> ImportSummary:
    subject = db.scalar(select(Subject).where(Subject.name == payload.subject))
    if subject is None:
        subject = Subject(name=payload.subject)
        db.add(subject)
        db.flush()

    if source_document is not None and source_document.subject_id != subject.id:
        raise ValueError("Lecture source does not belong to the imported subject")

    section = db.scalar(
        select(Section).where(
            Section.subject_id == subject.id,
            Section.name == payload.section,
        )
    )
    if section is None:
        section = Section(subject_id=subject.id, name=payload.section)
        db.add(section)
        db.flush()

    external_ids = [item.external_id for item in payload.questions]
    existing_ids = set(
        db.scalars(select(Question.external_id).where(Question.external_id.in_(external_ids)))
    )
    seen_ids = set(existing_ids)
    tag_cache: dict[str, Tag] = {
        tag.name: tag
        for tag in db.scalars(
            select(Tag).where(
                Tag.name.in_({tag for item in payload.questions for tag in item.tags})
            )
        )
    }

    imported = 0
    duplicates = 0
    for item in payload.questions:
        if item.external_id in seen_ids:
            duplicates += 1
            continue

        question_tags: list[Tag] = []
        for tag_name in item.tags:
            tag = tag_cache.get(tag_name)
            if tag is None:
                tag = Tag(name=tag_name)
                db.add(tag)
                tag_cache[tag_name] = tag
            question_tags.append(tag)

        question = Question(
            section_id=section.id,
            external_id=item.external_id,
            question_type=item.type,
            question=item.question,
            answer=item.answer,
            difficulty_level=item.difficulty_level,
            source=payload.source,
            source_page=None if item.source_page is None else str(item.source_page),
            source_document_id=(
                source_document.id if source_document is not None else None
            ),
            tags=question_tags,
            review_state=_new_review_state(),
        )
        db.add(question)
        seen_ids.add(item.external_id)
        imported += 1

    batch = ImportBatch(
        filename=filename or "upload.json",
        received_count=len(payload.questions),
        imported_count=imported,
        duplicate_count=duplicates,
        error_count=0,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    return ImportSummary(
        batch_id=batch.id,
        received=len(payload.questions),
        imported=imported,
        duplicates=duplicates,
        errors=0,
        subject_id=subject.id,
        section_id=section.id,
    )
