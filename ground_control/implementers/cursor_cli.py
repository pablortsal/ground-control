"""Cursor CLI implementer - delegates code writing to Cursor's CLI agent."""

from __future__ import annotations

import asyncio
import shutil

from ground_control.implementers.base import BaseImplementer, ImplementerResult


class CursorCLIImplementer(BaseImplementer):
    """Executes tasks via the Cursor CLI (cursor command)."""

    COMMAND = "cursor"

    async def execute(
        self,
        prompt: str,
        project_path: str,
        context: dict | None = None,
    ) -> ImplementerResult:
        if not await self.is_available():
            return ImplementerResult(
                success=False,
                error="Cursor CLI not found. Install it from https://cursor.com",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                self.COMMAND,
                "--project-path", project_path,
                "--prompt", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=600,  # 10 minute timeout
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
                    error=f"Cursor CLI exited with code {proc.returncode}: {stderr_text}",
                )

        except asyncio.TimeoutError:
            return ImplementerResult(
                success=False,
                error="Cursor CLI execution timed out after 600 seconds",
            )
        except Exception as e:
            return ImplementerResult(
                success=False,
                error=f"Failed to run Cursor CLI: {e}",
            )

    async def is_available(self) -> bool:
        return shutil.which(self.COMMAND) is not None
