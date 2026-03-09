"""Cursor CLI implementer - delegates code writing to Cursor's CLI agent."""

from __future__ import annotations

import asyncio
import shutil
import sys
import time

from ground_control.implementers.base import BaseImplementer, ImplementerResult


class CursorCLIImplementer(BaseImplementer):
    """Executes tasks via the Cursor Agent CLI (cursor agent command)."""

    COMMAND = "cursor"
    MAX_RETRIES = 2
    RETRY_DELAY = 10  # seconds

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

        # Try with retries for connection issues
        for attempt in range(self.MAX_RETRIES + 1):
            if attempt > 0:
                print(f"\n[Cursor CLI] Retry attempt {attempt}/{self.MAX_RETRIES}...")
                await asyncio.sleep(self.RETRY_DELAY)
            
            result = await self._execute_once(prompt, project_path, attempt)
            
            # If successful or a non-connection error, return
            if result.success or not self._is_connection_error(result.error):
                return result
            
            # Connection error - retry if we have attempts left
            if attempt < self.MAX_RETRIES:
                print(f"[Cursor CLI] Connection error detected, retrying in {self.RETRY_DELAY}s...", file=sys.stderr)
            else:
                print(f"[Cursor CLI] Max retries reached, giving up", file=sys.stderr)
                return result
        
        return result

    def _is_connection_error(self, error: str | None) -> bool:
        """Check if the error is a connection-related issue."""
        if not error:
            return False
        error_lower = error.lower()
        connection_keywords = [
            "connection lost",
            "reconnecting",
            "network",
            "timeout",
            "connection refused",
            "connection reset",
        ]
        return any(keyword in error_lower for keyword in connection_keywords)

    async def _execute_once(
        self,
        prompt: str,
        project_path: str,
        attempt: int,
    ) -> ImplementerResult:
        try:
            if attempt == 0:
                print(f"\n[Cursor CLI] Starting execution in {project_path}")
                print(f"[Cursor CLI] Command: cursor agent --print --force --workspace {project_path}")
                print(f"[Cursor CLI] Prompt length: {len(prompt)} characters\n")
                print(f"[Cursor CLI] Waiting for response...\n")
            
            start_time = time.time()
            
            proc = await asyncio.create_subprocess_exec(
                self.COMMAND,
                "agent",
                "--print",
                "--force",  # Auto-approve actions without prompting
                "--workspace", project_path,
                prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
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
                asyncio.create_task(read_stream(proc.stdout, "[Cursor OUT]", stdout_lines)),
                asyncio.create_task(read_stream(proc.stderr, "[Cursor ERR]", stderr_lines)),
            ]
            
            # Wait for process to complete with timeout
            try:
                return_code = await asyncio.wait_for(proc.wait(), timeout=600)
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                print(f"[Cursor CLI] Timeout after {elapsed:.1f}s, terminating process...", file=sys.stderr)
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                
                # Collect any remaining output
                await asyncio.wait(read_tasks, timeout=2)
                stderr_text = "\n".join(stderr_lines)
                
                return ImplementerResult(
                    success=False,
                    error=f"Cursor Agent timed out after {elapsed:.1f}s. Last stderr: {stderr_text[-500:] if stderr_text else 'none'}",
                )
            
            # Give stream readers a moment to finish
            await asyncio.wait(read_tasks, timeout=2)

            stdout_text = "\n".join(stdout_lines)
            stderr_text = "\n".join(stderr_lines)
            elapsed = time.time() - start_time

            print(f"\n[Cursor CLI] Process exited with code {return_code} after {elapsed:.1f}s\n")

            if return_code == 0:
                return ImplementerResult(
                    success=True,
                    output=stdout_text,
                )
            else:
                error_msg = f"Cursor Agent exited with code {return_code}"
                if stderr_text:
                    error_msg += f": {stderr_text}"
                return ImplementerResult(
                    success=False,
                    output=stdout_text,
                    error=error_msg,
                )

        except Exception as e:
            print(f"[Cursor CLI] Error: {e}", file=sys.stderr)
            return ImplementerResult(
                success=False,
                error=f"Failed to run Cursor Agent: {e}",
            )

    async def is_available(self) -> bool:
        return shutil.which(self.COMMAND) is not None
