from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-haiku-5.5"
DEFAULT_OPENROUTER_TIMEOUT_SECONDS = 300.0
DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS = 32000
logger = logging.getLogger("app.generation")


class OpenRouterError(RuntimeError):
    pass


class OpenRouterTimeoutError(OpenRouterError):
    pass


class OpenRouterHTTPError(OpenRouterError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_message = provider_message


class OpenRouterResponseError(OpenRouterError):
    pass


def _provider_http_error(response: httpx.Response) -> OpenRouterHTTPError:
    provider_message = None
    message = f"OpenRouter returned HTTP {response.status_code}"
    try:
        provider_message = response.json().get("error", {}).get("message")
        if provider_message:
            provider_message = str(provider_message)[:500]
            message = f"{message}: {provider_message}"
    except (ValueError, AttributeError):
        response_text = " ".join(response.text.splitlines()).strip()
        if response_text:
            provider_message = response_text[:500]
            message = f"{message}: {provider_message}"
    return OpenRouterHTTPError(
        message,
        status_code=response.status_code,
        provider_message=provider_message,
    )


def _safe_top_level_shape(document: Any) -> str:
    if isinstance(document, dict):
        keys = [
            re.sub(r"[^a-zA-Z0-9_-]", "?", str(key))[:40]
            for key in list(document)[:12]
        ]
        return f"object_keys={keys}"
    if isinstance(document, list):
        return f"array_length={len(document)}"
    return f"type={type(document).__name__}"


def generation_response_schema() -> dict[str, Any]:
    question = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "external_id": {"type": "string", "minLength": 1},
            "type": {
                "type": "string",
                "enum": ["recall", "concept", "problem", "code"],
            },
            "question": {"type": "string", "minLength": 1},
            "answer": {"type": "string", "minLength": 1},
            "difficulty_level": {
                "type": "integer",
                "minimum": 1,
                "maximum": 3,
            },
            "tags": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "source_page": {"type": ["integer", "string", "null"]},
        },
        "required": [
            "external_id",
            "type",
            "question",
            "answer",
            "difficulty_level",
            "tags",
            "source_page",
        ],
    }
    section = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "subject": {"type": "string", "minLength": 1},
            "section": {"type": "string", "minLength": 1},
            "source": {"type": ["string", "null"]},
            "questions": {
                "type": "array",
                "minItems": 1,
                "items": question,
            },
        },
        "required": [
            "schema_version",
            "subject",
            "section",
            "source",
            "questions",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sections": {"type": "array", "minItems": 1, "items": section}
        },
        "required": ["sections"],
    }


def _unwrap_expected_document(
    document: Any,
    expected_top_level_key: str | None,
) -> dict[str, Any] | None:
    if expected_top_level_key is None:
        return None
    current = document
    wrapper_keys = {"arguments", "data", "json", "output", "response", "result"}
    for _ in range(3):
        if isinstance(current, dict) and set(current) == {expected_top_level_key}:
            return current
        if not isinstance(current, dict) or len(current) != 1:
            return None
        key, value = next(iter(current.items()))
        if key not in wrapper_keys:
            return None
        current = value
    return None


def _parse_message_content(
    content: Any,
    *,
    finish_reason: str | None = None,
    expected_top_level_key: str | None = "sections",
    max_completion_tokens: int | None = None,
    completion_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> Any:
    if isinstance(content, dict):
        return (
            _unwrap_expected_document(content, expected_top_level_key) or content
        )
    if isinstance(content, list):
        if not all(
            isinstance(part, dict) and ("text" in part or "content" in part)
            for part in content
        ):
            return content
        content = "".join(
            str(part.get("text", part.get("content", "")))
            for part in content
        )
    if not isinstance(content, str) or not content.strip():
        raise OpenRouterResponseError(
            "OpenRouter returned a response without generated content"
        )

    text = content.strip().lstrip("\ufeff")
    parse_error: json.JSONDecodeError | None = None
    try:
        document = json.loads(text)
        return (
            _unwrap_expected_document(document, expected_top_level_key)
            or document
        )
    except json.JSONDecodeError as exc:
        parse_error = exc

    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    token_details = [f"finish_reason={finish_reason or 'unknown'}"]
    if max_completion_tokens is not None:
        token_details.append(f"max_completion_tokens={max_completion_tokens}")
    if completion_tokens is not None:
        token_details.append(f"completion_tokens={completion_tokens}")
    if reasoning_tokens is not None:
        token_details.append(f"reasoning_tokens={reasoning_tokens}")
    token_details.extend(
        (f"characters={len(text)}", f"fingerprint={fingerprint}")
    )
    response_details = ", ".join(token_details)

    fallback_document: Any = None
    found_fence = False
    for fenced in re.finditer(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        found_fence = True
        try:
            document = json.loads(fenced.group(1))
        except json.JSONDecodeError:
            continue
        expected = _unwrap_expected_document(document, expected_top_level_key)
        if expected is not None:
            return expected
        if fallback_document is None:
            fallback_document = document

    if found_fence:
        if fallback_document is not None:
            return fallback_document
        assert parse_error is not None
        if finish_reason in {"length", "max_tokens"}:
            raise OpenRouterResponseError(
                "OpenRouter truncated the generated JSON after reaching its "
                f"completion limit ({response_details}). Increase "
                "OPENROUTER_MAX_COMPLETION_TOKENS or generate a smaller "
                "lecture section."
            ) from parse_error
        raise OpenRouterResponseError(
            "OpenRouter returned malformed JSON inside a Markdown fence "
            f"({response_details})"
        ) from parse_error

    decoder = json.JSONDecoder()
    json_start = re.search(r"[\{\[]", text)
    if json_start is not None:
        try:
            document, _ = decoder.raw_decode(text[json_start.start():])
        except json.JSONDecodeError:
            document = None
        if document is not None:
            return (
                _unwrap_expected_document(document, expected_top_level_key)
                or document
            )

    assert parse_error is not None
    if finish_reason in {"length", "max_tokens"}:
        raise OpenRouterResponseError(
            "OpenRouter truncated the generated JSON after reaching its "
            f"completion limit ({response_details}). Increase "
            "OPENROUTER_MAX_COMPLETION_TOKENS or generate a smaller lecture "
            "section."
        ) from parse_error
    raise OpenRouterResponseError(
        "OpenRouter returned malformed JSON "
        f"({response_details}): {parse_error.msg}"
    ) from parse_error


@dataclass(frozen=True)
class OpenRouterClient:
    api_key: str
    base_url: str = DEFAULT_OPENROUTER_BASE_URL
    timeout_seconds: float = DEFAULT_OPENROUTER_TIMEOUT_SECONDS
    max_completion_tokens: int = DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS
    transport: httpx.AsyncBaseTransport | None = None

    async def generate(
        self,
        *,
        prompt: str,
        model: str,
        response_schema: dict[str, Any] | None = None,
        schema_name: str = "study_question_sections",
        operation_name: str = "questions",
        allow_json_fallback: bool = False,
    ) -> Any:
        selected_schema = response_schema or generation_response_schema()
        schema_properties = sorted(selected_schema.get("properties", {}))
        logger.info(
            "openrouter_request stage=openrouter_request model=%r operation=%s "
            "schema_name=%r schema_top_level_properties=%s structured_output=true "
            "max_completion_tokens=%s",
            model,
            operation_name,
            schema_name,
            schema_properties,
            self.max_completion_tokens,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": selected_schema,
                },
            },
            "max_completion_tokens": self.max_completion_tokens,
        }
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            async def post(request_body: dict[str, Any]) -> httpx.Response:
                try:
                    response = await client.post(
                        endpoint, headers=headers, json=request_body
                    )
                    response.raise_for_status()
                    return response
                except httpx.TimeoutException as exc:
                    raise OpenRouterTimeoutError(
                        f"OpenRouter timed out while generating {operation_name}"
                    ) from exc
                except httpx.HTTPStatusError as exc:
                    raise _provider_http_error(exc.response) from exc
                except httpx.HTTPError as exc:
                    raise OpenRouterHTTPError(
                        "Could not connect to OpenRouter"
                    ) from exc

            try:
                response = await post(body)
            except OpenRouterHTTPError as exc:
                if not allow_json_fallback or exc.status_code != 400:
                    raise
                logger.warning(
                    "openrouter_structured_output_rejected status=%s "
                    "provider_message=%r model=%r operation=%s "
                    "fallback=json_object",
                    exc.status_code,
                    exc.provider_message,
                    model,
                    operation_name,
                )
                fallback_body = {
                    **body,
                    "response_format": {"type": "json_object"},
                }
                response = await post(fallback_body)

        try:
            response_document = response.json()
        except ValueError as exc:
            raise OpenRouterResponseError(
                "OpenRouter returned an invalid HTTP response"
            ) from exc
        try:
            choice = response_document["choices"][0]
            message = choice["message"]
            content = message.get("parsed", message.get("content"))
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterResponseError(
                "OpenRouter returned a response without generated content"
            ) from exc
        refusal = message.get("refusal")
        if refusal:
            raise OpenRouterResponseError("OpenRouter refused the generation request")
        usage = response_document.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        completion_tokens = usage.get("completion_tokens")
        completion_details = usage.get("completion_tokens_details")
        if not isinstance(completion_details, dict):
            completion_details = {}
        reasoning_tokens = completion_details.get("reasoning_tokens")
        completion_tokens = (
            completion_tokens if isinstance(completion_tokens, int) else None
        )
        reasoning_tokens = (
            reasoning_tokens if isinstance(reasoning_tokens, int) else None
        )
        try:
            document = _parse_message_content(
                content,
                finish_reason=finish_reason,
                max_completion_tokens=self.max_completion_tokens,
                completion_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
            )
        except OpenRouterResponseError as exc:
            logger.error(
                "openrouter_response stage=response_parsing model=%r "
                "schema_name=%r finish_reason=%r exception_type=%s message=%r",
                model,
                schema_name,
                finish_reason,
                type(exc).__name__,
                str(exc),
            )
            raise
        logger.info(
            "openrouter_response stage=response_parsing model=%r schema_name=%r "
            "finish_reason=%r generated_response_%s",
            model,
            schema_name,
            finish_reason,
            _safe_top_level_shape(document),
        )
        return document


async def request_openrouter(
    *,
    prompt: str,
    model: str,
    api_key: str,
    base_url: str = DEFAULT_OPENROUTER_BASE_URL,
    max_completion_tokens: int = DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS,
    timeout_seconds: float = DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
    transport: httpx.AsyncBaseTransport | None = None,
    response_schema: dict[str, Any] | None = None,
    schema_name: str = "study_question_sections",
    operation_name: str = "questions",
    allow_json_fallback: bool = False,
) -> Any:
    client = OpenRouterClient(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_completion_tokens=max_completion_tokens,
        transport=transport,
    )
    return await client.generate(
        prompt=prompt,
        model=model,
        response_schema=response_schema,
        schema_name=schema_name,
        operation_name=operation_name,
        allow_json_fallback=allow_json_fallback,
    )
