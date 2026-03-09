"""Claude Code CLI implementer - delegates code writing to Claude Code."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys

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
            print(f"\n[Claude Code] Starting execution in {project_path}")
            print(f"[Claude Code] Command: claude -p <prompt> --output-format text --max-turns 50")
            print(f"[Claude Code] Prompt length: {len(prompt)} characters\n")
            print(f"[Claude Code] Waiting for response...\n")
            
            proc = await asyncio.create_subprocess_exec(
                self.COMMAND,
                "-p", prompt,
                "--output-format", "text",
                "--max-turns", "50",
                "--dangerously-skip-permissions",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
                # Important: Set environment to avoid interactive prompts
                env={**os.environ, "CLAUDE_NO_PROMPT": "1"},
            )

            # Stream output in real-time
            stdout_lines = []
            stderr_lines = []
            
            async def read_stream(stream, prefix, lines_collector):
                try:
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace").rstrip()
                        if text:  # Only print non-empty lines
                            print(f"{prefix} {text}", flush=True)
                            lines_collector.append(text)
                except Exception as e:
                    print(f"{prefix} Stream error: {e}", flush=True)
            
            # Start reading streams in background tasks
            read_tasks = [
                asyncio.create_task(read_stream(proc.stdout, "[Claude OUT]", stdout_lines)),
                asyncio.create_task(read_stream(proc.stderr, "[Claude ERR]", stderr_lines)),
            ]
            
            # Wait for process to complete with timeout
            try:
                return_code = await asyncio.wait_for(proc.wait(), timeout=600)
            except asyncio.TimeoutError:
                print("[Claude Code] Timeout reached, terminating process...", file=sys.stderr)
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                raise
            
            # Give stream readers a moment to finish
            await asyncio.wait(read_tasks, timeout=2)

            stdout_text = "\n".join(stdout_lines)
            stderr_text = "\n".join(stderr_lines)

            print(f"\n[Claude Code] Process exited with code {return_code}\n")

            if return_code == 0:
                return ImplementerResult(
                    success=True,
                    output=stdout_text,
                )
            else:
                return ImplementerResult(
                    success=False,
                    output=stdout_text,
                    error=f"Claude Code exited with code {return_code}: {stderr_text}",
                )

        except asyncio.TimeoutError:
            print("[Claude Code] Execution timed out after 600 seconds", file=sys.stderr)
            return ImplementerResult(
                success=False,
                error="Claude Code execution timed out after 600 seconds",
            )
        except Exception as e:
            print(f"[Claude Code] Error: {e}", file=sys.stderr)
            return ImplementerResult(
                success=False,
                error=f"Failed to run Claude Code: {e}",
            )

    async def is_available(self) -> bool:
        return shutil.which(self.COMMAND) is not None
