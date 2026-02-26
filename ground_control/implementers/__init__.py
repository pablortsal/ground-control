"""Implementer abstractions - wrappers for code-writing tools."""

from ground_control.implementers.base import BaseImplementer, ImplementerResult
from ground_control.implementers.cursor_cli import CursorCLIImplementer
from ground_control.implementers.claude_code import ClaudeCodeImplementer

IMPLEMENTERS: dict[str, type[BaseImplementer]] = {
    "cursor_cli": CursorCLIImplementer,
    "claude_code": ClaudeCodeImplementer,
}


def get_implementer(name: str, **kwargs) -> BaseImplementer:
    """Get an implementer by name."""
    if name not in IMPLEMENTERS:
        raise ValueError(
            f"Unknown implementer: {name}. Available: {list(IMPLEMENTERS.keys())}"
        )
    return IMPLEMENTERS[name](**kwargs)

__all__ = [
    "BaseImplementer",
    "ImplementerResult",
    "CursorCLIImplementer",
    "ClaudeCodeImplementer",
    "get_implementer",
    "IMPLEMENTERS",
]
