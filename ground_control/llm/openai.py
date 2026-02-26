"""OpenAI LLM provider."""

from __future__ import annotations

import json
import os

from openai import AsyncOpenAI

from ground_control.llm.base import BaseLLMProvider, LLMResponse

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(BaseLLMProvider):
    """LLM provider backed by the OpenAI API."""

    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        super().__init__(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            default_model=default_model or DEFAULT_MODEL,
        )
        self._client = AsyncOpenAI(api_key=self.api_key)

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

        full_messages = list(messages)
        if system:
            full_messages.insert(0, {"role": "system", "content": system})

        response = await self._client.chat.completions.create(
            model=resolved_model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
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
        resolved_model = self._resolve_model(model)

        full_messages = list(messages)
        if system:
            full_messages.insert(0, {"role": "system", "content": system})

        response = await self._client.chat.completions.create(
            model=resolved_model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        return json.loads(content)
