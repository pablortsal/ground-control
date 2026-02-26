"""Abstract base class for code implementers."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class ImplementerResult:
    """Result from an implementer execution."""

    success: bool
    output: str = ""
    error: str | None = None
    files_changed: list[str] | None = None


class BaseImplementer(abc.ABC):
    """Interface for tools that write code in a project (Cursor CLI, Claude Code, etc.)."""

    @abc.abstractmethod
    async def execute(
        self,
        prompt: str,
        project_path: str,
        context: dict | None = None,
    ) -> ImplementerResult:
        """Execute a task using this implementer.

        Args:
            prompt: The full prompt including agent instructions and task details.
            project_path: Absolute path to the project repository.
            context: Optional metadata (task info, agent name, etc.).

        Returns:
            ImplementerResult with success status and output.
        """
        ...

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """Check if this implementer's CLI tool is installed and accessible."""
        ...
