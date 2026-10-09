from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from app.schemas import (
    GeneratedNote,
    GeneratedNoteSection,
    StructuredConceptNote,
    StructuredFormulaNote,
    StructuredGeneratedNote,
    StructuredNoteGenerationDocument,
    StructuredProcedureNote,
    StructuredTheoremNote,
)
from app.services.generation import (
    PROMPTS_ROOT,
    ExtractedPdf,
    GenerationConfigurationError,
    select_subject_profile,
)
from app.services.openrouter import (
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS,
    DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
    request_openrouter,
)


class GeneratedNoteOutputError(ValueError):
    pass


def note_generation_response_schema() -> dict[str, Any]:
    # Keep the provider-facing schema intentionally flat. Some OpenRouter
    # providers reject Pydantic's $defs/oneOf/discriminator representation.
    # The discriminated Pydantic models below remain the authoritative
    # type-specific validator after the response is received.
    note = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {
                "type": "string",
                "enum": ["formula", "theorem", "concept", "procedure"],
            },
            "title": {"type": "string", "minLength": 1, "maxLength": 255},
            "meaning": {"type": "string"},
            "why_it_matters": {"type": ["string", "null"]},
            "purpose": {"type": "string"},
            "formula": {"type": "string"},
            "variables": {"type": "array", "items": {"type": "string"}},
            "example": {"type": "string"},
            "statement": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
            "important_condition": {"type": ["string", "null"]},
            "source_page": {"type": ["integer", "string", "null"]},
        },
        "required": ["type", "title", "source_page"],
    }
    section = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "subject": {"type": "string", "minLength": 1},
            "section": {"type": "string", "minLength": 1},
            "notes": {"type": "array", "minItems": 1, "items": note},
        },
        "required": ["subject", "section", "notes"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sections": {"type": "array", "minItems": 1, "items": section}
        },
        "required": ["sections"],
    }


def load_note_prompts(
    subject_name: str, prompts_root: Path = PROMPTS_ROOT
) -> tuple[str, str, str]:
    profile = select_subject_profile(subject_name)
    try:
        base_prompt = (prompts_root / "base_note_generation.md").read_text(
            encoding="utf-8"
        )
        subject_prompt = (prompts_root / "subjects" / profile.filename).read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise GenerationConfigurationError(
            f"Could not load note generation prompt file: {exc.filename}"
        ) from exc
    return base_prompt, subject_prompt, profile.key


def compose_note_generation_prompt(
    *,
    subject_name: str,
    pdf_filename: str,
    pdf_text: str,
    section_name: str | None,
    prompts_root: Path = PROMPTS_ROOT,
) -> tuple[str, str]:
    base_prompt, subject_prompt, profile = load_note_prompts(
        subject_name, prompts_root
    )
    section_instruction = (
        f'Create exactly one section named "{section_name}".'
        if section_name
        else "Detect one or more meaningful sections from the lecture material."
    )
    prompt = "\n\n".join(
        (
            base_prompt.strip(),
            "# Subject profile (topic priorities only)\n\n" + subject_prompt.strip(),
            "# Generation context\n\n"
            f"Subject (copy exactly): {subject_name}\n"
            f"Source PDF filename: {pdf_filename}\n"
            f"Section instruction: {section_instruction}",
            "# Extracted lecture content\n\n" + pdf_text,
        )
    )
    return prompt, profile


def _parse_document(raw_output: Any) -> Any:
    if isinstance(raw_output, (dict, list)):
        return raw_output
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise GeneratedNoteOutputError("The provider returned empty note content")
    text = raw_output.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeneratedNoteOutputError(
            f"The provider returned invalid note JSON: {exc.msg}"
        ) from exc


def render_structured_note(note: StructuredGeneratedNote) -> GeneratedNote:
    if isinstance(note, StructuredConceptNote):
        parts = ["### Meaning", note.meaning]
        if note.why_it_matters:
            parts.extend(("### Why it matters", note.why_it_matters))
    elif isinstance(note, StructuredFormulaNote):
        parts = ["### Purpose", note.purpose, "### Formula", note.formula]
        if note.variables:
            parts.extend(
                ("### Variables", "\n".join(f"- {item}" for item in note.variables))
            )
        parts.extend(("### Simple Example", note.example))
    elif isinstance(note, StructuredTheoremNote):
        parts = [
            "### Meaning",
            note.meaning,
            "### Statement",
            note.statement,
            "### Simple Example",
            note.example,
        ]
    elif isinstance(note, StructuredProcedureNote):
        parts = [
            "### Purpose",
            note.purpose,
            "### Steps",
            "\n".join(
                f"{index}. {step}" for index, step in enumerate(note.steps, start=1)
            ),
        ]
        if note.important_condition:
            parts.extend(("### Important condition", note.important_condition))
    else:  # pragma: no cover - the discriminated Pydantic union is exhaustive.
        raise TypeError(f"Unsupported structured note: {type(note).__name__}")
    return GeneratedNote(
        type=note.type,
        title=note.title,
        content_markdown="\n\n".join(parts),
        source_page=note.source_page,
    )


def validate_rendered_note_sections(
    sections: list[GeneratedNoteSection],
    *,
    subject_name: str,
    page_count: int,
    requested_section: str | None,
) -> list[GeneratedNoteSection]:
    if any(section.subject != subject_name for section in sections):
        raise GeneratedNoteOutputError(
            "Generated note subject does not match the selected subject"
        )
    if requested_section and (
        len(sections) != 1 or sections[0].section != requested_section
    ):
        raise GeneratedNoteOutputError(
            "Generated notes do not match the specified section name"
        )

    seen: set[tuple[str, str, str]] = set()
    for section in sections:
        for note in section.notes:
            key = (
                section.section.casefold(),
                note.type,
                " ".join(note.title.casefold().split()),
            )
            if key in seen:
                raise GeneratedNoteOutputError(
                    f"Generated notes repeat title {note.title!r}"
                )
            seen.add(key)
            if note.source_page is None:
                continue
            numbers = [int(value) for value in re.findall(r"\d+", str(note.source_page))]
            if not numbers or any(number < 1 or number > page_count for number in numbers):
                raise GeneratedNoteOutputError(
                    f"Note {note.title!r} has an invalid source_page"
                )
    return sections


def validate_generated_note_sections(
    raw_output: Any,
    *,
    subject_name: str,
    page_count: int,
    requested_section: str | None,
) -> list[GeneratedNoteSection]:
    document = _parse_document(raw_output)
    if not isinstance(document, dict) or set(document) != {"sections"}:
        raise GeneratedNoteOutputError(
            'Generated note JSON must contain only a top-level "sections" field'
        )
    raw_sections = document["sections"]
    if not isinstance(raw_sections, list) or not raw_sections:
        raise GeneratedNoteOutputError("Generated note JSON contains no sections")

    try:
        typed_document = StructuredNoteGenerationDocument.model_validate(document)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_url=False)[:8]
        )
        raise GeneratedNoteOutputError(
            f"Generated note JSON failed validation: {errors}"
        ) from exc
    sections = [
        GeneratedNoteSection(
            subject=section.subject,
            section=section.section,
            notes=[render_structured_note(note) for note in section.notes],
        )
        for section in typed_document.sections
    ]
    return validate_rendered_note_sections(
        sections,
        subject_name=subject_name,
        page_count=page_count,
        requested_section=requested_section,
    )


ProviderRequest = Callable[..., Awaitable[Any]]


async def generate_note_preview(
    *,
    subject_name: str,
    pdf_filename: str,
    extracted_pdf: ExtractedPdf,
    section_name: str | None,
    model: str,
    api_key: str,
    base_url: str = DEFAULT_OPENROUTER_BASE_URL,
    timeout_seconds: float = DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
    max_completion_tokens: int = DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS,
    provider_request: ProviderRequest = request_openrouter,
) -> tuple[list[GeneratedNoteSection], str]:
    if not api_key.strip():
        raise GenerationConfigurationError(
            "OPENROUTER_API_KEY is not configured on the backend"
        )
    if not model.strip():
        raise GenerationConfigurationError(
            "Choose a model or configure OPENROUTER_MODEL on the backend"
        )
    prompt, profile = compose_note_generation_prompt(
        subject_name=subject_name,
        pdf_filename=pdf_filename,
        pdf_text=extracted_pdf.text,
        section_name=section_name,
    )
    raw_output = await provider_request(
        prompt=prompt,
        model=model.strip(),
        api_key=api_key.strip(),
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_completion_tokens=max_completion_tokens,
        response_schema=note_generation_response_schema(),
        schema_name="study_note_sections",
        operation_name="notes",
        allow_json_fallback=True,
    )
    sections = validate_generated_note_sections(
        raw_output,
        subject_name=subject_name,
        page_count=extracted_pdf.pages,
        requested_section=section_name,
    )
    return sections, profile
