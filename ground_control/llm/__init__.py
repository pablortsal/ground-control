"""LLM provider abstractions and implementations."""

from ground_control.llm.base import BaseLLMProvider, LLMResponse
from ground_control.llm.anthropic import AnthropicProvider
from ground_control.llm.openai import OpenAIProvider

PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str, **kwargs) -> BaseLLMProvider:
    """Get an LLM provider by name."""
    if name not in PROVIDERS:
        raise ValueError(f"Unknown LLM provider: {name}. Available: {list(PROVIDERS.keys())}")
    return PROVIDERS[name](**kwargs)

__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "AnthropicProvider",
    "OpenAIProvider",
    "get_provider",
    "PROVIDERS",
]
