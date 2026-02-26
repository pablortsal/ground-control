"""Abstract base class for LLM providers."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict | None = None


class BaseLLMProvider(abc.ABC):
    """Interface that every LLM provider must implement."""

    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        self.api_key = api_key
        self.default_model = default_model

    @abc.abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> LLMResponse:
        """Send a chat completion request and return the response."""
        ...

    @abc.abstractmethod
    async def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> dict:
        """Send a chat completion request expecting a JSON response.

        Returns the parsed JSON dict directly.
        """
        ...

    def _resolve_model(self, model: str | None) -> str:
        if model:
            return model
        if self.default_model:
            return self.default_model
        raise ValueError("No model specified and no default_model configured.")
