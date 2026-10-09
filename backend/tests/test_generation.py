import asyncio
import json
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Question, Section, Subject
from app.main import generation_config, openrouter_max_completion_tokens
from app.services.generation import (
    PROMPTS_ROOT,
    ExtractedPdf,
    GeneratedOutputError,
    GenerationConfigurationError,
    compose_generation_prompt,
    extract_pdf_text,
    generate_preview,
    load_generation_prompts,
    select_subject_profile,
    validate_generated_sections,
)
from app.services.importer import import_questions
from app.services.openrouter import (
    DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS,
    DEFAULT_OPENROUTER_MODEL,
    OpenRouterHTTPError,
    OpenRouterResponseError,
    OpenRouterTimeoutError,
    request_openrouter,
)


def test_haiku_is_the_backend_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert DEFAULT_OPENROUTER_MODEL == "anthropic/claude-haiku-5.5"
    assert generation_config()["default_model"] == DEFAULT_OPENROUTER_MODEL


def test_openrouter_completion_budget_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_MAX_COMPLETION_TOKENS", raising=False)
    assert DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS == 32000
    assert openrouter_max_completion_tokens() == 32000

    monkeypatch.setenv("OPENROUTER_MAX_COMPLETION_TOKENS", "48000")
    assert openrouter_max_completion_tokens() == 48000

    monkeypatch.setenv("OPENROUTER_MAX_COMPLETION_TOKENS", "unlimited")
    with pytest.raises(GenerationConfigurationError, match="must be an integer"):
        openrouter_max_completion_tokens()


def generated_section(
    *,
    section: str = "Memory",
    external_id: str = "efes-memory-capacity",
    source_page: int | None = 1,
) -> dict:
    return {
        "schema_version": "1.0",
        "subject": "Electronics for Embedded Systems",
        "section": section,
        "source": "lecture.pdf",
        "questions": [
            {
                "external_id": external_id,
                "type": "problem",
                "question": "Calculate the memory capacity.",
                "answer": "Use \\(N_{words} \\times n_{bits}\\).",
                "difficulty_level": 2,
                "tags": ["memory", "capacity"],
                "source_page": source_page,
            }
        ],
    }


def extracted_pdf() -> ExtractedPdf:
    return ExtractedPdf(
        text="[PDF PAGE 1]\nMemory organization and capacity",
        pages=2,
        characters=48,
        estimated_tokens=12,
    )


def add_text_page(writer: PdfWriter, text: str) -> None:
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


def test_pdf_extraction_preserves_real_page_markers() -> None:
    writer = PdfWriter()
    add_text_page(writer, "SRAM timing")
    add_text_page(writer, "Read cycle")
    buffer = BytesIO()
    writer.write(buffer)

    extracted = extract_pdf_text(buffer.getvalue())
    assert extracted.pages == 2
    assert extracted.text == (
        "[PDF PAGE 1]\nSRAM timing\n\n[PDF PAGE 2]\nRead cycle"
    )
    assert extracted.estimated_tokens > 0


def test_loads_finalized_base_and_subject_prompt_files() -> None:
    base_prompt, subject_prompt, profile = load_generation_prompts(
        "Electronics for Embedded Systems"
    )
    assert base_prompt == (PROMPTS_ROOT / "base_question_generation.md").read_text(
        encoding="utf-8"
    )
    assert subject_prompt == (
        PROMPTS_ROOT / "subjects" / "electronics_embedded.md"
    ).read_text(encoding="utf-8")
    assert profile.key == "electronics_embedded"


@pytest.mark.parametrize(
    "subject_name, expected_profile",
    [
        (
            "Modeling and Optimization of Embedded Systems",
            "modeling_optimization",
        ),
        ("Electronics for Embedded Systems", "electronics_embedded"),
        ("Computer Architecture", "computer_architecture"),
        ("Testing and Certification", "testing_certification"),
    ],
)
def test_specialized_subject_profile_mapping(
    subject_name: str, expected_profile: str
) -> None:
    assert select_subject_profile(subject_name).key == expected_profile


def test_unknown_subject_uses_general_profile() -> None:
    assert select_subject_profile("Linear Algebra").key == "general"
    assert select_subject_profile("Electronic Music").key == "general"


def test_prompt_order_is_stable_and_subject_is_dynamic(tmp_path: Path) -> None:
    subjects_root = tmp_path / "subjects"
    subjects_root.mkdir()
    (tmp_path / "base_question_generation.md").write_text(
        "BASE PROMPT SENTINEL", encoding="utf-8"
    )
    (subjects_root / "electronics_embedded.md").write_text(
        "SUBJECT PROFILE SENTINEL", encoding="utf-8"
    )

    prompt, profile = compose_generation_prompt(
        subject_name="Electronics for Embedded Systems",
        pdf_filename="lecture.pdf",
        pdf_text="[PDF PAGE 1]\nSRAM timing",
        section_name="SRAM",
        prompts_root=tmp_path,
    )
    assert profile == "electronics_embedded"
    assert prompt.startswith("BASE PROMPT SENTINEL")
    assert 'Create exactly one section named "SRAM"' in prompt
    assert "Subject (copy exactly): Electronics for Embedded Systems" in prompt
    assert "[PDF PAGE 1]\nSRAM timing" in prompt
    assert (
        prompt.index("BASE PROMPT SENTINEL")
        < prompt.index("SUBJECT PROFILE SENTINEL")
        < prompt.index("# Generation context")
        < prompt.index("Subject (copy exactly): Electronics for Embedded Systems")
        < prompt.index("# Extracted lecture content")
        < prompt.index("[PDF PAGE 1]")
    )


def test_generated_json_validation_handles_multiple_sections() -> None:
    result = validate_generated_sections(
        {
            "sections": [
                generated_section(),
                generated_section(
                    section="SRAM", external_id="efes-sram-read", source_page=2
                ),
            ]
        },
        subject_name="Electronics for Embedded Systems",
        page_count=2,
        requested_section=None,
    )
    assert [section.section for section in result] == ["Memory", "SRAM"]
    assert all(section.schema_version == "1.0" for section in result)


@pytest.mark.parametrize(
    "raw_output, message",
    [
        ("not json", "invalid JSON"),
        ({"sections": []}, "did not contain any sections"),
        (
            {"sections": [generated_section(source_page=99)]},
            "invalid source_page",
        ),
    ],
)
def test_invalid_provider_response_is_rejected(raw_output, message: str) -> None:
    with pytest.raises(GeneratedOutputError, match=message):
        validate_generated_sections(
            raw_output,
            subject_name="Electronics for Embedded Systems",
            page_count=2,
            requested_section=None,
        )


@pytest.mark.parametrize(
    "raw_output",
    [generated_section(), [generated_section()]],
)
def test_generated_json_normalizes_unambiguous_section_envelopes(raw_output) -> None:
    sections = validate_generated_sections(
        raw_output,
        subject_name="Electronics for Embedded Systems",
        page_count=2,
        requested_section=None,
    )
    assert [section.section for section in sections] == ["Memory"]


def test_generated_json_rejects_a_bare_question_object() -> None:
    question = generated_section()["questions"][0]
    with pytest.raises(
        GeneratedOutputError,
        match=r'top-level object containing only "sections".*external_id',
    ):
        validate_generated_sections(
            question,
            subject_name="Electronics for Embedded Systems",
            page_count=2,
            requested_section=None,
        )


def test_generated_json_rejects_fields_outside_import_schema() -> None:
    section = generated_section()
    section["questions"][0]["confidence"] = 0.9
    with pytest.raises(GeneratedOutputError, match="unsupported question fields"):
        validate_generated_sections(
            {"sections": [section]},
            subject_name="Electronics for Embedded Systems",
            page_count=2,
            requested_section=None,
        )


def test_generated_json_rejects_wrong_subject() -> None:
    section = generated_section()
    section["subject"] = "A Different Subject"
    with pytest.raises(GeneratedOutputError, match="does not match"):
        validate_generated_sections(
            {"sections": [section]},
            subject_name="Electronics for Embedded Systems",
            page_count=2,
            requested_section=None,
        )


def test_missing_api_key_stops_before_provider_call() -> None:
    provider_called = False

    async def provider_request(**kwargs):
        nonlocal provider_called
        provider_called = True
        return {"sections": [generated_section()]}

    with pytest.raises(GenerationConfigurationError, match="OPENROUTER_API_KEY"):
        asyncio.run(
            generate_preview(
                subject_name="Electronics for Embedded Systems",
                pdf_filename="lecture.pdf",
                extracted_pdf=extracted_pdf(),
                section_name=None,
                model="test/model",
                api_key="",
                provider_request=provider_request,
            )
        )
    assert provider_called is False


def test_openrouter_request_uses_structured_output_without_real_network() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://mock.openrouter.test/api/v1/chat/completions"
        )
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "test/model"
        assert body["max_completion_tokens"] == 32000
        assert body["response_format"]["type"] == "json_schema"
        schema = body["response_format"]["json_schema"]
        assert schema["name"] == "study_question_sections"
        assert set(schema["schema"]["properties"]) == {"sections"}
        assert "external_id" not in schema["schema"]["properties"]
        question_schema = schema["schema"]["properties"]["sections"]["items"]
        question_schema = question_schema["properties"]["questions"]["items"]
        assert "external_id" in question_schema["properties"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"sections": [generated_section()]}
                            )
                        }
                    }
                ]
            },
        )

    document = asyncio.run(
        request_openrouter(
            prompt="Generate",
            model="test/model",
            api_key="secret",
            base_url="https://mock.openrouter.test/api/v1/",
            transport=httpx.MockTransport(handler),
        )
    )
    assert document["sections"][0]["section"] == "Memory"


def test_openrouter_logs_safe_schema_and_response_shape(caplog) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                generated_section()["questions"][0]
                            )
                        },
                    }
                ]
            },
        )

    with caplog.at_level("INFO", logger="app.generation"):
        document = asyncio.run(
            request_openrouter(
                prompt="Generate",
                model="test/model",
                api_key="secret-value",
                transport=httpx.MockTransport(handler),
            )
        )

    assert document["external_id"] == "efes-memory-capacity"
    assert "schema_name='study_question_sections'" in caplog.text
    assert "schema_top_level_properties=['sections']" in caplog.text
    assert "generated_response_object_keys=['external_id'" in caplog.text
    assert "stage=response_parsing" in caplog.text
    assert "secret-value" not in caplog.text


def test_openrouter_timeout_is_reported_separately() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider took too long", request=request)

    with pytest.raises(OpenRouterTimeoutError, match="timed out"):
        asyncio.run(
            request_openrouter(
                prompt="Generate",
                model="test/model",
                api_key="secret",
                transport=httpx.MockTransport(handler),
            )
        )


def test_openrouter_http_error_is_safe_and_useful() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"message": "Rate limit exceeded"}},
        )

    with pytest.raises(OpenRouterHTTPError, match="HTTP 429.*Rate limit exceeded") as error:
        asyncio.run(
            request_openrouter(
                prompt="Generate",
                model="test/model",
                api_key="secret",
                transport=httpx.MockTransport(handler),
            )
        )
    assert "secret" not in str(error.value)
    assert error.value.status_code == 429
    assert error.value.provider_message == "Rate limit exceeded"


def test_openrouter_malformed_json_content_is_rejected() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{not-json"}}]},
        )

    with pytest.raises(OpenRouterResponseError, match="malformed JSON"):
        asyncio.run(
            request_openrouter(
                prompt="Generate",
                model="test/model",
                api_key="secret",
                transport=httpx.MockTransport(handler),
            )
        )


def test_openrouter_does_not_salvage_a_nested_question_from_broken_envelope() -> None:
    question = json.dumps(generated_section()["questions"][0])
    broken_envelope = '{"sections": [{"questions": [' + question + "]}"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": broken_envelope},
                    }
                ]
            },
        )

    with pytest.raises(OpenRouterResponseError, match="malformed JSON"):
        asyncio.run(
            request_openrouter(
                prompt="Generate",
                model="test/model",
                api_key="secret",
                transport=httpx.MockTransport(handler),
            )
        )


@pytest.mark.parametrize(
    "content",
    [
        "Here is the requested JSON:\n```json\n{\"sections\": []}\n```",
        "Generated result:\n{\"sections\": []}\nEnd of result.",
        '{"result": {"sections": []}}',
        (
            "Example:\n```json\n{\"example\": true}\n```\n"
            "Result:\n```json\n{\"sections\": []}\n```"
        ),
        [
            {
                "type": "text",
                "text": "```json\n{\"sections\": []}\n```",
            }
        ],
    ],
)
def test_openrouter_recovers_json_from_provider_wrappers(content) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": content},
                    }
                ]
            },
        )

    document = asyncio.run(
        request_openrouter(
            prompt="Generate",
            model="test/model",
            api_key="secret",
            transport=httpx.MockTransport(handler),
        )
    )
    assert document == {"sections": []}


def test_openrouter_reports_truncated_json_without_logging_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": '```json\n{"sections": ['
                        },
                    }
                ],
                "usage": {
                    "completion_tokens": 32000,
                    "completion_tokens_details": {"reasoning_tokens": 27000},
                },
            },
        )

    with pytest.raises(OpenRouterResponseError, match="truncated.*fingerprint") as error:
        asyncio.run(
            request_openrouter(
                prompt="Generate",
                model="test/model",
                api_key="secret",
                transport=httpx.MockTransport(handler),
            )
        )
    message = str(error.value)
    assert '{"sections": [' not in message
    assert "max_completion_tokens=32000" in message
    assert "completion_tokens=32000" in message
    assert "reasoning_tokens=27000" in message
    assert "OPENROUTER_MAX_COMPLETION_TOKENS" in message


def test_preview_does_not_write_and_approved_sections_use_existing_importer(
    db: Session,
) -> None:
    db.add(Subject(name="Electronics for Embedded Systems"))
    db.commit()

    async def provider_request(**kwargs):
        schema = kwargs["response_schema"]
        assert kwargs["max_completion_tokens"] == 32000
        assert kwargs["schema_name"] == "study_question_sections"
        assert kwargs["operation_name"] == "questions"
        assert set(schema["properties"]) == {"sections"}
        assert "external_id" not in schema["properties"]
        return {
            "sections": [
                generated_section(),
                generated_section(
                    section="SRAM",
                    external_id="efes-sram-read",
                    source_page=2,
                ),
            ]
        }

    sections, profile = asyncio.run(
        generate_preview(
            subject_name="Electronics for Embedded Systems",
            pdf_filename="lecture.pdf",
            extracted_pdf=extracted_pdf(),
            section_name=None,
            model="test/model",
            api_key="secret",
            provider_request=provider_request,
        )
    )

    assert profile == "electronics_embedded"
    assert len(sections) == 2
    assert db.scalar(select(func.count(Question.id))) == 0
    assert db.scalar(select(func.count(Section.id))) == 0

    summaries = [
        import_questions(db, section, f"generated-{index}.json")
        for index, section in enumerate(sections, start=1)
    ]
    assert sum(summary.imported for summary in summaries) == 2
    assert db.scalar(select(func.count(Question.id))) == 2
    assert db.scalar(select(func.count(Section.id))) == 2
