from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


QuestionType = Literal["recall", "concept", "problem", "code"]
NoteType = Literal["formula", "theorem", "concept", "procedure"]
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


class PdfEstimate(BaseModel):
    filename: str
    pages: int
    extracted_characters: int
    estimated_input_tokens: int


class GenerationPreview(BaseModel):
    provider: Literal["openrouter"] = "openrouter"
    model: str
    profile: str
    source: str
    pages: int
    extracted_characters: int
    estimated_input_tokens: int
    validation_status: Literal["valid"] = "valid"
    source_document_id: int
    sections: list[ImportPayload]


class GeneratedNote(BaseModel):
    type: NoteType
    title: str = Field(min_length=1, max_length=255)
    content_markdown: str = Field(min_length=1)
    source_page: int | str | None = None
    duplicate: bool = False

    @field_validator("title", "content_markdown")
    @classmethod
    def strip_note_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


def _strip_required_note_field(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class StructuredNoteBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    source_page: int | str | None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return _strip_required_note_field(value)


class StructuredConceptNote(StructuredNoteBase):
    type: Literal["concept"]
    meaning: str = Field(min_length=1)
    why_it_matters: str | None = None

    @field_validator("meaning")
    @classmethod
    def strip_meaning(cls, value: str) -> str:
        return _strip_required_note_field(value)

    @field_validator("why_it_matters")
    @classmethod
    def strip_optional_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class StructuredFormulaNote(StructuredNoteBase):
    type: Literal["formula"]
    purpose: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    variables: list[str]
    example: str = Field(min_length=1)

    @field_validator("purpose", "formula", "example")
    @classmethod
    def strip_required_fields(cls, value: str) -> str:
        return _strip_required_note_field(value)

    @field_validator("variables")
    @classmethod
    def normalize_variables(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            clean = value.strip()
            if not clean:
                raise ValueError("variables must not contain blank entries")
            normalized.append(clean)
        return normalized


class StructuredTheoremNote(StructuredNoteBase):
    type: Literal["theorem"]
    meaning: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    example: str = Field(min_length=1)

    @field_validator("meaning", "statement", "example")
    @classmethod
    def strip_required_fields(cls, value: str) -> str:
        return _strip_required_note_field(value)


class StructuredProcedureNote(StructuredNoteBase):
    type: Literal["procedure"]
    purpose: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    important_condition: str | None = None

    @field_validator("purpose")
    @classmethod
    def strip_purpose(cls, value: str) -> str:
        return _strip_required_note_field(value)

    @field_validator("steps")
    @classmethod
    def normalize_steps(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            clean = value.strip()
            if not clean:
                raise ValueError("steps must not contain blank entries")
            normalized.append(clean)
        return normalized

    @field_validator("important_condition")
    @classmethod
    def strip_optional_condition(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


StructuredGeneratedNote = Annotated[
    StructuredConceptNote
    | StructuredFormulaNote
    | StructuredTheoremNote
    | StructuredProcedureNote,
    Field(discriminator="type"),
]


class StructuredGeneratedNoteSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=255)
    section: str = Field(min_length=1, max_length=255)
    notes: list[StructuredGeneratedNote] = Field(min_length=1)

    @field_validator("subject", "section")
    @classmethod
    def strip_names(cls, value: str) -> str:
        return _strip_required_note_field(value)


class StructuredNoteGenerationDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[StructuredGeneratedNoteSection] = Field(min_length=1)


class GeneratedNoteSection(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    section: str = Field(min_length=1, max_length=255)
    notes: list[GeneratedNote] = Field(min_length=1)

    @field_validator("subject", "section")
    @classmethod
    def strip_note_names(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class NoteGenerationPreview(BaseModel):
    provider: Literal["openrouter"] = "openrouter"
    model: str
    profile: str
    source: str
    pages: int
    extracted_characters: int
    estimated_input_tokens: int
    validation_status: Literal["valid"] = "valid"
    source_document_id: int
    sections: list[GeneratedNoteSection]


class NoteSaveRequest(BaseModel):
    subject_id: int
    source_document_id: int | None = None
    sections: list[GeneratedNoteSection] = Field(min_length=1)


class NoteSaveSummary(BaseModel):
    received: int
    saved: int
    duplicates: int
    section_ids: list[int]


class NoteUpdate(BaseModel):
    note_type: NoteType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content_markdown: str | None = Field(default=None, min_length=1)
    source_page: str | int | None = None

    @field_validator("title", "content_markdown")
    @classmethod
    def reject_blank_note_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value.strip() if value is not None else None


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
