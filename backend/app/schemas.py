from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


QuestionType = Literal["recall", "concept", "problem", "code"]
RatingName = Literal["again", "hard", "good", "easy"]


class ImportQuestion(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    type: QuestionType
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    difficulty_level: int = Field(default=2, ge=1, le=3)
    tags: list[str] = Field(default_factory=list)
    source_page: str | int | None = None

    @field_validator("external_id")
    @classmethod
    def normalize_external_id(cls, value: str) -> str:
        value = value.strip()
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("question", "answer")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            clean = value.strip().lower()
            if not clean:
                raise ValueError("tags must not be blank")
            if len(clean) > 100:
                raise ValueError("tags must be at most 100 characters")
            if clean not in normalized:
                normalized.append(clean)
        return normalized


class ImportPayload(BaseModel):
    schema_version: Literal["1.0"]
    subject: str = Field(min_length=1, max_length=255)
    section: str = Field(min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=255)
    questions: list[ImportQuestion] = Field(min_length=1)

    @field_validator("subject", "section")
    @classmethod
    def strip_names(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ImportSummary(BaseModel):
    batch_id: int
    received: int
    imported: int
    duplicates: int
    errors: int
    subject_id: int
    section_id: int


class BatchFileImportResult(BaseModel):
    filename: str
    received: int = 0
    imported: int = 0
    duplicates: int = 0
    errors: list[str] = Field(default_factory=list)


class BatchImportSummary(BaseModel):
    files_received: int
    files_processed: int
    questions_received: int
    questions_imported: int
    duplicates: int
    errors: int
    files: list[BatchFileImportResult]


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class QuestionUpdate(BaseModel):
    section_id: int | None = None
    question_type: QuestionType | None = None
    question: str | None = Field(default=None, min_length=1)
    answer: str | None = Field(default=None, min_length=1)
    difficulty_level: int | None = Field(default=None, ge=1, le=3)
    source: str | None = None
    source_page: str | None = None
    tags: list[str] | None = None

    @field_validator("question", "answer")
    @classmethod
    def reject_blank_content(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        normalized = []
        for value in values:
            clean = value.strip().lower()
            if not clean or len(clean) > 100:
                raise ValueError("tags must contain 1 to 100 characters")
            if clean not in normalized:
                normalized.append(clean)
        return normalized


class RateRequest(BaseModel):
    rating: RatingName


class RateResponse(BaseModel):
    question_id: int
    rating: RatingName
    reviewed_at: datetime
    next_due_at: datetime
    state: str


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
