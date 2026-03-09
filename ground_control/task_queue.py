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
        running_tasks: set[asyncio.Task] = set()
        
        while True:
            pending = await self.state.get_pending_tasks(run_id)
            
            # Launch new tasks up to the concurrency limit
            launched = 0
            for task in pending:
                if len(running_tasks) >= self.max_parallel:
                    break
                await self.state.update_task_status(task["id"], TaskStatus.QUEUED)
                t = asyncio.create_task(self._run_single(task, executor))
                running_tasks.add(t)
                launched += 1
            
            if launched > 0:
                all_tasks = await self.state.list_tasks(run_id)
                total = len(all_tasks)
                done_count = sum(
                    1 for t in all_tasks
                    if t["status"] in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value)
                )
                console.print(
                    f"  [dim]Progress: {done_count}/{total} done, "
                    f"{len(running_tasks)} running, {len(pending) - launched} waiting[/]"
                )
            
            if running_tasks:
                done, running_tasks = await asyncio.wait(
                    running_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            elif not pending:
                # Nothing running and nothing pending - we're done
                break
            else:
                # Pending tasks exist but none could be launched (shouldn't happen)
                await asyncio.sleep(0.5)

        return list(self._results.values())

    async def _run_single(
        self,
        task: dict,
        executor: Callable[[dict], Coroutine[Any, Any, TaskResult]],
    ) -> None:
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
