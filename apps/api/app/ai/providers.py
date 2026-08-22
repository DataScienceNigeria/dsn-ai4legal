"""Provider adapters behind one interface.

Model capability, pricing and availability move quickly, and some matters will
require a locally hosted model. Every model call goes through this layer so a
route can be changed by configuration rather than by code (PRD section 1.2 and
goal LOP-G-07). Adding a provider means adding one class to this module and one
row to the route table; nothing else in the platform changes.

OpenAI is the configured commercial provider. A self-hosted open-weights model
serves restricted content, and an offline adapter keeps every workflow runnable
with no external reach at all.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.ai.routing import ModelRoute
from app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class ModelRequest:
    system: str
    user_content: str
    output_schema: dict[str, Any]
    schema_name: str = "output"
    max_tokens: int = settings.dsnlai_ai_max_tokens
    effort: str = settings.dsnlai_ai_effort
    tools: list[dict] = field(default_factory=list)

@dataclass
class ModelResponse:
    parsed: dict[str, Any]
    raw_text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    model_version: str | None = None
    refused: bool = False
    refusal_reason: str | None = None

class ProviderUnavailable(RuntimeError):
    """The route exists in policy but the provider cannot serve the call."""

class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

    def complete(self, request: ModelRequest, route: ModelRoute) -> ModelResponse: ...

def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Structured outputs require every object to close itself.

    A schema that allows extra properties lets a model return a field the
    platform will not read, which is how ungrounded content leaks through a
    contract that looked strict.
    """
    if schema.get("type") == "object":
        schema = dict(schema)
        schema["additionalProperties"] = False
        properties = schema.get("properties", {})
        schema["required"] = list(properties.keys())
        schema["properties"] = {k: _strict_schema(v) for k, v in properties.items()}
    elif schema.get("type") == "array" and "items" in schema:
        schema = dict(schema)
        schema["items"] = _strict_schema(schema["items"])
    return schema

class OpenAIProvider:
    """OpenAI, through the official SDK.

    Structured output is requested with a strict JSON schema, so the response is
    a validated document rather than prose that has to be parsed. A model that
    declines returns a refusal, which the capability layer surfaces as an
    explicit refusal rather than an empty answer.
    """

    name = "openai"

    def __init__(self) -> None:
        self._client = None

    def available(self) -> bool:
        return bool(settings.openai_api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url or None,
                timeout=settings.dsnlai_ai_timeout_seconds,
                max_retries=2,
            )
        return self._client

    def complete(self, request: ModelRequest, route: ModelRoute) -> ModelResponse:
        import openai

        client = self._get_client()
        started = time.perf_counter()

        payload: dict[str, Any] = {
            "model": route.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "strict": True,
                    "schema": _strict_schema(request.output_schema),
                },
            },
            "max_completion_tokens": request.max_tokens,
        }
        if settings.dsnlai_ai_send_effort:
            payload["reasoning_effort"] = request.effort

        try:
            response = client.chat.completions.create(**payload)
        except openai.APIStatusError as exc:
            raise ProviderUnavailable(
                f"OpenAI returned {exc.status_code}: {exc.message}"
            ) from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailable("OpenAI could not be reached.") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = response.choices[0]
        message = choice.message

        refusal = getattr(message, "refusal", None)
        if refusal:
            return ModelResponse(
                parsed={},
                raw_text="",
                latency_ms=latency_ms,
                model_version=response.model,
                refused=True,
                refusal_reason=refusal,
            )
        if choice.finish_reason == "length":
            raise ProviderUnavailable(
                "The response was truncated before it was complete, so it cannot be trusted."
            )

        text = message.content or ""
        usage = response.usage
        return ModelResponse(
            parsed=json.loads(text) if text else {},
            raw_text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            model_version=response.model,
        )

class SelfHostedProvider:
    """A locally hosted open-weights model on an OpenAI-compatible server.

    This is the only route permitted for restricted content, because nothing
    leaves the platform network (PRD section 13.4).
    """

    name = "self_hosted"

    def available(self) -> bool:
        if not settings.dsnlai_ai_local_base_url:
            return False
        try:
            reply = httpx.get(f"{settings.dsnlai_ai_local_base_url}/models", timeout=2.0)
            return reply.status_code == 200
        except httpx.HTTPError:
            return False

    def complete(self, request: ModelRequest, route: ModelRoute) -> ModelResponse:
        started = time.perf_counter()
        try:
            reply = httpx.post(
                f"{settings.dsnlai_ai_local_base_url}/chat/completions",
                json={
                    "model": route.model,
                    "messages": [
                        {"role": "system", "content": request.system},
                        {"role": "user", "content": request.user_content},
                    ],
                    "max_tokens": request.max_tokens,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": request.schema_name,
                            "strict": True,
                            "schema": _strict_schema(request.output_schema),
                        },
                    },
                },
                timeout=settings.dsnlai_ai_timeout_seconds,
            )
            reply.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"The self-hosted model could not be reached: {exc}"
            ) from exc

        body = reply.json()
        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        return ModelResponse(
            parsed=json.loads(text) if text else {},
            raw_text=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
            model_version=route.model,
        )

class OfflineProvider:
    """A deterministic fallback that reaches nothing.

    Every workflow in this platform has a manual fallback and the AI layer is no
    exception (PRD section 3.2, reversible by design). This provider returns a
    refusal rather than an invented answer, which is the correct behaviour when
    no route is configured. It also makes the whole platform runnable, and
    testable, with no external dependency and no spend.
    """

    name = "offline"

    def available(self) -> bool:
        return True

    def complete(self, request: ModelRequest, route: ModelRoute) -> ModelResponse:
        digest = hashlib.sha256(request.user_content.encode()).hexdigest()[:16]
        return ModelResponse(
            parsed={},
            raw_text="",
            latency_ms=1,
            model_version="offline-deterministic",
            refused=True,
            refusal_reason=(
                "No model route is configured, so no grounded answer can be produced. "
                "The documented manual path for this capability applies. "
                f"Request digest {digest}."
            ),
        )

PROVIDERS: dict[str, Provider] = {
    "openai": OpenAIProvider(),
    "self_hosted": SelfHostedProvider(),
    "offline": OfflineProvider(),
}

def available_routes() -> set[str]:
    """Route names whose provider is configured and reachable."""
    from app.ai.routing import ROUTES

    return {name for name, route in ROUTES.items() if PROVIDERS[route.provider].available()}
