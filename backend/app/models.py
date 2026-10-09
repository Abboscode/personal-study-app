from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


question_tags = Table(
    "question_tags",
    Base.metadata,
    Column("question_id", ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Subject(TimestampMixin, Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    sections: Mapped[list[Section]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )
    lecture_sources: Mapped[list[LectureSource]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )
    notes: Mapped[list[Note]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )


class LectureSource(Base):
    __tablename__ = "lecture_sources"
    __table_args__ = (
        UniqueConstraint(
            "subject_id", "file_hash", name="uq_lecture_source_subject_hash"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subject: Mapped[Subject] = relationship(back_populates="lecture_sources")
    questions: Mapped[list[Question]] = relationship(back_populates="source_document")
    notes: Mapped[list[Note]] = relationship(back_populates="source_document")


class Section(TimestampMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("subject_id", "name", name="uq_section_subject_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    subject: Mapped[Subject] = relationship(back_populates="sections")
    questions: Mapped[list[Question]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )
    notes: Mapped[list[Note]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    questions: Mapped[list[Question]] = relationship(
        secondary=question_tags, back_populates="tags"
    )


class Question(TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('recall', 'concept', 'problem', 'code')",
            name="ck_question_type",
        ),
        CheckConstraint("difficulty_level BETWEEN 1 AND 3", name="ck_difficulty_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    source: Mapped[str | None] = mapped_column(String(255))
    source_page: Mapped[str | None] = mapped_column(String(100))
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("lecture_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    section: Mapped[Section] = relationship(back_populates="questions")
    source_document: Mapped[LectureSource | None] = relationship(
        back_populates="questions"
    )
    tags: Mapped[list[Tag]] = relationship(secondary=question_tags, back_populates="questions")
    review_state: Mapped[ReviewState] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )
    review_history: Mapped[list[ReviewHistory]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Note(TimestampMixin, Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "note_type IN ('formula', 'theorem', 'concept', 'procedure')",
            name="ck_note_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("lecture_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_page: Mapped[str | None] = mapped_column(String(100))
    note_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)

    subject: Mapped[Subject] = relationship(back_populates="notes")
    section: Mapped[Section] = relationship(back_populates="notes")
    source_document: Mapped[LectureSource | None] = relationship(
        back_populates="notes"
    )


class ReviewState(Base):
    __tablename__ = "review_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    stability: Mapped[float | None] = mapped_column(Float)
    fsrs_difficulty: Mapped[float | None] = mapped_column(Float)
    scheduled_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    elapsed_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    card_json: Mapped[str] = mapped_column(Text, nullable=False)

    question: Mapped[Question] = relationship(back_populates="review_state")


class ReviewHistory(Base):
    __tablename__ = "review_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    previous_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_state_before: Mapped[str] = mapped_column(Text, nullable=False)
    review_state_after: Mapped[str] = mapped_column(Text, nullable=False)

    question: Mapped[Question] = relationship(back_populates="review_history")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
