"""Claude Code CLI implementer - delegates code writing to Claude Code."""

from __future__ import annotations

import asyncio
import shutil

from ground_control.implementers.base import BaseImplementer, ImplementerResult


class ClaudeCodeImplementer(BaseImplementer):
    """Executes tasks via the Claude Code CLI (claude command)."""

    COMMAND = "claude"

    async def execute(
        self,
        prompt: str,
        project_path: str,
        context: dict | None = None,
    ) -> ImplementerResult:
        if not await self.is_available():
            return ImplementerResult(
                success=False,
                error="Claude Code CLI not found. Install it: npm install -g @anthropic-ai/claude-code",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                self.COMMAND,
                "-p", prompt,
                "--output-format", "text",
                "--max-turns", "50",
                "--dangerously-skip-permissions",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=600,
            )

            stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

            if proc.returncode == 0:
                return ImplementerResult(
                    success=True,
                    output=stdout_text,
                )
            else:
                return ImplementerResult(
                    success=False,
                    output=stdout_text,
                    error=f"Claude Code exited with code {proc.returncode}: {stderr_text}",
                )

        except asyncio.TimeoutError:
            return ImplementerResult(
                success=False,
                error="Claude Code execution timed out after 600 seconds",
            )
        except Exception as e:
            return ImplementerResult(
                success=False,
                error=f"Failed to run Claude Code: {e}",
            )

    async def is_available(self) -> bool:
        return shutil.which(self.COMMAND) is not None
