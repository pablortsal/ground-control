"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

import json
import os

from anthropic import AsyncAnthropic

from ground_control.llm.base import BaseLLMProvider, LLMResponse

DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider(BaseLLMProvider):
    """LLM provider backed by the Anthropic API."""

    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        super().__init__(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            default_model=default_model or DEFAULT_MODEL,
        )
        self._client = AsyncAnthropic(api_key=self.api_key)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> LLMResponse:
        resolved_model = self._resolve_model(model)

        kwargs: dict = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            raw=response.model_dump(),
        )

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> dict:
        json_system = (system or "") + (
            "\n\nYou MUST respond with valid JSON only. No markdown fences, no extra text."
        )
        response = await self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system=json_system.strip(),
        )
        return json.loads(response.content)
