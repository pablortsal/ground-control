"""Parallel task execution queue with dependency resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from rich.console import Console

from ground_control.state import StateStore, TaskStatus

console = Console()


@dataclass
class TaskResult:
    task_id: str
    success: bool
    output: str = ""
    error: str | None = None


class TaskQueue:
    """Executes tasks in parallel respecting dependencies and concurrency limits."""

    def __init__(
        self,
        state: StateStore,
        max_parallel: int = 3,
    ):
        self.state = state
        self.max_parallel = max_parallel
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._results: dict[str, TaskResult] = {}
        self._completed_event = asyncio.Event()

    async def execute_all(
        self,
        run_id: str,
        executor: Callable[[dict], Coroutine[Any, Any, TaskResult]],
    ) -> list[TaskResult]:
        """Execute all pending tasks for a run, respecting dependencies.

        Args:
            run_id: The run to execute tasks for.
            executor: Async callable that takes a task dict and returns a TaskResult.
        """
        while True:
            pending = await self.state.get_pending_tasks(run_id)
            if not pending:
                all_tasks = await self.state.list_tasks(run_id)
                still_running = any(
                    t["status"] in (TaskStatus.RUNNING.value, TaskStatus.QUEUED.value)
                    for t in all_tasks
                )
                if still_running:
                    await asyncio.sleep(0.5)
                    continue
                break

            batch = []
            for task in pending:
                await self.state.update_task_status(task["id"], TaskStatus.QUEUED)
                batch.append(self._run_single(task, executor))

            await asyncio.gather(*batch)

        return list(self._results.values())

    async def _run_single(
        self,
        task: dict,
        executor: Callable[[dict], Coroutine[Any, Any, TaskResult]],
    ) -> None:
        async with self._semaphore:
            task_id = task["id"]
            await self.state.update_task_status(task_id, TaskStatus.RUNNING)
            console.print(f"  [bold blue]▶[/] Running task: {task['title']}")

            try:
                result = await executor(task)
                self._results[task_id] = result

                if result.success:
                    await self.state.update_task_status(
                        task_id, TaskStatus.COMPLETED, result=result.output
                    )
                    console.print(f"  [bold green]✓[/] Completed: {task['title']}")
                else:
                    await self.state.update_task_status(
                        task_id, TaskStatus.FAILED, result=result.error
                    )
                    console.print(f"  [bold red]✗[/] Failed: {task['title']}: {result.error}")

            except Exception as e:
                error_msg = str(e)
                self._results[task_id] = TaskResult(
                    task_id=task_id, success=False, error=error_msg
                )
                await self.state.update_task_status(
                    task_id, TaskStatus.FAILED, result=error_msg
                )
                console.print(f"  [bold red]✗[/] Error in {task['title']}: {error_msg}")
