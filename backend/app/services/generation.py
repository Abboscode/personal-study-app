from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.schemas import ImportPayload
from app.services.openrouter import (
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS,
    DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
    generation_response_schema,
    request_openrouter,
)


PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


class PdfExtractionError(ValueError):
    pass


class GenerationConfigurationError(ValueError):
    pass


class GeneratedOutputError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPdf:
    text: str
    pages: int
    characters: int
    estimated_tokens: int


@dataclass(frozen=True)
class SubjectProfile:
    key: str
    filename: str


SUBJECT_PROFILES = {
    "modeling_optimization": SubjectProfile(
        key="modeling_optimization", filename="modeling_optimization.md"
    ),
    "electronics_embedded": SubjectProfile(
        key="electronics_embedded", filename="electronics_embedded.md"
    ),
    "computer_architecture": SubjectProfile(
        key="computer_architecture", filename="computer_architecture.md"
    ),
    "testing_certification": SubjectProfile(
        key="testing_certification", filename="testing_certification.md"
    ),
    "general": SubjectProfile(key="general", filename="general.md"),
}

SUBJECT_PROFILE_BY_NAME = {
    "modeling and optimization of embedded systems": "modeling_optimization",
    "modeling and optimisation of embedded systems": "modeling_optimization",
    "systemc": "modeling_optimization",
    "electronics for embedded systems": "electronics_embedded",
    "computer architecture": "computer_architecture",
    "computer architectures": "computer_architecture",
    "testing and certification": "testing_certification",
}


def estimate_tokens(text: str) -> int:
    """A deliberately simple, provider-independent estimate."""
    return math.ceil(len(text) / 4) if text else 0


def extract_pdf_text(raw: bytes) -> ExtractedPdf:
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PdfExtractionError("Password-protected PDFs are not supported")

        page_blocks: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                page_blocks.append(f"[PDF PAGE {page_number}]\n{text}")
    except PdfExtractionError:
        raise
    except (PyPdfError, OSError, ValueError) as exc:
        raise PdfExtractionError("The uploaded file is not a readable PDF") from exc

    if not page_blocks:
        raise PdfExtractionError(
            "No selectable text was found. Scanned PDFs need OCR before upload."
        )

    text = "\n\n".join(page_blocks)
    return ExtractedPdf(
        text=text,
        pages=len(reader.pages),
        characters=len(text),
        estimated_tokens=estimate_tokens(text),
    )


def select_subject_profile(subject_name: str) -> SubjectProfile:
    normalized_name = " ".join(
        subject_name.casefold().replace("&", " and ").split()
    )
    profile_key = SUBJECT_PROFILE_BY_NAME.get(normalized_name, "general")
    return SUBJECT_PROFILES[profile_key]


def load_generation_prompts(
    subject_name: str, prompts_root: Path = PROMPTS_ROOT
) -> tuple[str, str, SubjectProfile]:
    profile = select_subject_profile(subject_name)
    try:
        base_prompt = (prompts_root / "base_question_generation.md").read_text(
            encoding="utf-8"
        )
        subject_prompt = (prompts_root / "subjects" / profile.filename).read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise GenerationConfigurationError(
            f"Could not load generation prompt file: {exc.filename}"
        ) from exc
    return base_prompt, subject_prompt, profile


def compose_generation_prompt(
    *,
    subject_name: str,
    pdf_filename: str,
    pdf_text: str,
    section_name: str | None,
    prompts_root: Path = PROMPTS_ROOT,
) -> tuple[str, str]:
    base_prompt, subject_prompt, profile = load_generation_prompts(
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
            f"# Course-specific priorities\n\n{subject_prompt.strip()}",
            "# Generation context\n\n"
            f"Subject (copy exactly): {subject_name}\n"
            f"Source PDF filename (copy into `source`): {pdf_filename}\n"
            f"Section instruction: {section_instruction}",
            "# Extracted lecture content\n\n" + pdf_text,
        )
    )
    return prompt, profile.key


def _parse_generated_document(raw_output: Any) -> Any:
    if isinstance(raw_output, (dict, list)):
        return raw_output
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise GeneratedOutputError("The provider returned empty generated content")
    text = raw_output.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeneratedOutputError(f"The provider returned invalid JSON: {exc.msg}") from exc


def _safe_document_shape(document: Any) -> str:
    if isinstance(document, dict):
        keys = [
            re.sub(r"[^a-zA-Z0-9_-]", "?", str(key))[:40]
            for key in list(document)[:8]
        ]
        return f"object keys={keys}"
    if isinstance(document, list):
        return f"array length={len(document)}"
    return type(document).__name__


def _normalize_sections_envelope(document: Any) -> Any:
    required_section_keys = {"schema_version", "subject", "section", "questions"}

    def is_section(value: Any) -> bool:
        return isinstance(value, dict) and required_section_keys <= set(value)

    if is_section(document):
        return {"sections": [document]}
    if (
        isinstance(document, list)
        and document
        and all(is_section(item) for item in document)
    ):
        return {"sections": document}
    return document


def validate_generated_sections(
    raw_output: Any,
    *,
    subject_name: str,
    page_count: int,
    requested_section: str | None,
) -> list[ImportPayload]:
    document = _normalize_sections_envelope(_parse_generated_document(raw_output))
    if not isinstance(document, dict) or set(document) != {"sections"}:
        raise GeneratedOutputError(
            'Generated JSON must be a top-level object containing only "sections"; '
            f"received {_safe_document_shape(document)}"
        )
    raw_sections = document["sections"]
    if not isinstance(raw_sections, list) or not raw_sections:
        raise GeneratedOutputError("Generated JSON did not contain any sections")

    section_keys = {"schema_version", "subject", "section", "source", "questions"}
    question_keys = {
        "external_id",
        "type",
        "question",
        "answer",
        "difficulty_level",
        "tags",
        "source_page",
    }
    for section_index, section in enumerate(raw_sections):
        if not isinstance(section, dict):
            continue
        extra_section_keys = set(section) - section_keys
        if extra_section_keys:
            raise GeneratedOutputError(
                "Generated JSON contains unsupported section fields: "
                + ", ".join(sorted(extra_section_keys))
            )
        questions = section.get("questions")
        if not isinstance(questions, list):
            continue
        for question_index, question in enumerate(questions):
            if not isinstance(question, dict):
                continue
            extra_question_keys = set(question) - question_keys
            if extra_question_keys:
                raise GeneratedOutputError(
                    "Generated JSON contains unsupported question fields at "
                    f"sections.{section_index}.questions.{question_index}: "
                    + ", ".join(sorted(extra_question_keys))
                )

    try:
        sections = [ImportPayload.model_validate(section) for section in raw_sections]
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_url=False)[:8]
        )
        raise GeneratedOutputError(f"Generated JSON failed import validation: {errors}") from exc

    if any(section.subject != subject_name for section in sections):
        raise GeneratedOutputError(
            "Generated JSON subject does not match the selected subject"
        )
    if requested_section and (
        len(sections) != 1 or sections[0].section != requested_section
    ):
        raise GeneratedOutputError(
            "Generated JSON does not match the specified section name"
        )
    section_names = [section.section.casefold() for section in sections]
    if len(section_names) != len(set(section_names)):
        raise GeneratedOutputError("Generated JSON contains duplicate section names")

    external_ids: set[str] = set()
    for section in sections:
        for question in section.questions:
            if question.external_id in external_ids:
                raise GeneratedOutputError(
                    f"Generated JSON repeats external_id {question.external_id!r}"
                )
            external_ids.add(question.external_id)
            if question.source_page is None:
                continue
            numbers = [int(value) for value in re.findall(r"\d+", str(question.source_page))]
            if not numbers or any(number < 1 or number > page_count for number in numbers):
                raise GeneratedOutputError(
                    f"Question {question.external_id!r} has an invalid source_page"
                )
    return sections


ProviderRequest = Callable[..., Awaitable[Any]]


async def generate_preview(
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
) -> tuple[list[ImportPayload], str]:
    if not api_key.strip():
        raise GenerationConfigurationError(
            "OPENROUTER_API_KEY is not configured on the backend"
        )
    if not model.strip():
        raise GenerationConfigurationError(
            "Choose a model or configure OPENROUTER_MODEL on the backend"
        )
    prompt, profile = compose_generation_prompt(
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
        response_schema=generation_response_schema(),
        schema_name="study_question_sections",
        operation_name="questions",
    )
    sections = validate_generated_sections(
        raw_output,
        subject_name=subject_name,
        page_count=extracted_pdf.pages,
        requested_section=section_name,
    )
    return sections, profile
