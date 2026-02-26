"""Main orchestration engine that ties everything together."""

from __future__ import annotations

import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from ground_control.agent_manager import AgentDefinition, AgentManager
from ground_control.config import ProjectConfig, load_project_config, find_project_config, load_gc_config
from ground_control.implementers import get_implementer
from ground_control.implementers.base import BaseImplementer
from ground_control.llm import get_provider
from ground_control.llm.base import BaseLLMProvider
from ground_control.planner import Planner, PlannedTask
from ground_control.state import StateStore, RunStatus, TaskStatus
from ground_control.task_queue import TaskQueue, TaskResult
from ground_control.ticket_sources import get_ticket_source
from ground_control.ticket_sources.base import Ticket, TicketStatus

console = Console()


class Orchestrator:
    """Central engine that coordinates planning, agents, and execution."""

    def __init__(
        self,
        project_config: ProjectConfig,
        agent_manager: AgentManager,
        state: StateStore,
        llm: BaseLLMProvider,
    ):
        self.project_config = project_config
        self.agent_manager = agent_manager
        self.state = state
        self.llm = llm
        self._implementers: dict[str, BaseImplementer] = {}

    @classmethod
    async def from_project_name(cls, project_name: str, base_dir: str | Path | None = None) -> "Orchestrator":
        """Create an orchestrator from a project name, loading all configs."""
        base_dir = Path(base_dir) if base_dir else Path.cwd()
        gc_config = load_gc_config(base_dir)

        project_path = find_project_config(project_name, base_dir / gc_config.projects_dir)
        project_config = load_project_config(project_path)

        agent_manager = AgentManager(base_dir / gc_config.agents_dir)
        agent_manager.load_all()

        state = StateStore(base_dir / gc_config.db_path)
        await state.initialize()

        llm = get_provider(project_config.settings.default_llm)

        return cls(
            project_config=project_config,
            agent_manager=agent_manager,
            state=state,
            llm=llm,
        )

    async def run(self) -> str:
        """Execute a full orchestration run. Returns the run ID."""
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        config = self.project_config

        console.print(Panel(
            f"[bold]Project:[/] {config.name}\n"
            f"[bold]Repo:[/] {config.repo_path}\n"
            f"[bold]Run ID:[/] {run_id}",
            title="[bold cyan]Ground Control[/]",
            border_style="cyan",
        ))

        await self.state.create_run(
            run_id=run_id,
            project_name=config.name,
            config_snapshot=config.model_dump(),
        )

        # Phase 1: Load tickets
        console.print("\n[bold yellow]Phase 1:[/] Loading tickets...")
        await self.state.update_run_status(run_id, RunStatus.PLANNING)

        ticket_source = get_ticket_source(
            config.ticket_source.type,
            path=config.ticket_source.path,
        )
        tickets = await ticket_source.load_tickets()

        open_tickets = [t for t in tickets if t.status == TicketStatus.OPEN]
        console.print(f"  Found {len(tickets)} tickets ({len(open_tickets)} open)")

        if not open_tickets:
            console.print("[yellow]No open tickets to process.[/]")
            await self.state.update_run_status(run_id, RunStatus.COMPLETED)
            return run_id

        # Phase 2: Plan
        console.print("\n[bold yellow]Phase 2:[/] Planning tasks with LLM...")
        agents = [
            self.agent_manager.get(name)
            for name in config.agents
        ]

        planner = Planner(self.llm, config)
        planned_tasks = await planner.plan(open_tickets, agents)
        console.print(f"  Planned {len(planned_tasks)} tasks")

        for pt in planned_tasks:
            await self.state.create_task(
                task_id=pt.id,
                run_id=run_id,
                title=pt.title,
                description=pt.description,
                ticket_id=pt.ticket_id,
                assigned_agent=pt.assigned_agent,
                priority=pt.priority,
                dependencies=pt.dependencies,
            )

        # Phase 3: Execute
        console.print(f"\n[bold yellow]Phase 3:[/] Executing tasks (max parallel: {config.settings.max_parallel_agents})...")
        await self.state.update_run_status(run_id, RunStatus.RUNNING)

        queue = TaskQueue(
            state=self.state,
            max_parallel=config.settings.max_parallel_agents,
        )

        results = await queue.execute_all(run_id, self._execute_task)

        # Phase 4: Report
        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        final_status = RunStatus.COMPLETED if failed == 0 else RunStatus.FAILED
        await self.state.update_run_status(run_id, final_status)

        console.print(Panel(
            f"[bold green]Completed:[/] {succeeded}  [bold red]Failed:[/] {failed}  "
            f"[bold]Total:[/] {len(results)}",
            title=f"[bold cyan]Run {run_id} - {'SUCCESS' if failed == 0 else 'PARTIAL FAILURE'}[/]",
            border_style="green" if failed == 0 else "red",
        ))

        return run_id

    async def _execute_task(self, task: dict) -> TaskResult:
        """Execute a single task using the assigned agent and implementer."""
        task_id = task["id"]
        agent_name = task.get("assigned_agent", "developer")

        try:
            agent_def = self.agent_manager.get(agent_name)
        except KeyError:
            return TaskResult(
                task_id=task_id,
                success=False,
                error=f"Agent '{agent_name}' not found",
            )

        implementer_name = (
            agent_def.implementer or self.project_config.settings.implementer
        )

        execution_id = await self.state.create_execution(
            task_id=task_id,
            run_id=task["run_id"],
            agent_name=agent_name,
            implementer=implementer_name,
        )

        prompt = self._build_prompt(task, agent_def)

        await self.state.add_log(
            task_id=task_id,
            message=f"Starting execution with agent '{agent_name}' via '{implementer_name}'",
            agent_name=agent_name,
        )

        try:
            implementer = self._get_implementer(implementer_name)
            result = await implementer.execute(
                prompt=prompt,
                project_path=self.project_config.repo_path,
                context={
                    "task": task,
                    "agent": agent_def.name,
                    "project": self.project_config.name,
                },
            )

            await self.state.finish_execution(
                execution_id=execution_id,
                status="completed" if result.success else "failed",
                output=result.output,
                error=result.error,
            )

            await self.state.add_log(
                task_id=task_id,
                message=f"Execution {'completed' if result.success else 'failed'}",
                level="info" if result.success else "error",
                agent_name=agent_name,
            )

            return TaskResult(
                task_id=task_id,
                success=result.success,
                output=result.output,
                error=result.error,
            )

        except Exception as e:
            error_msg = str(e)
            await self.state.finish_execution(
                execution_id=execution_id,
                status="failed",
                error=error_msg,
            )
            await self.state.add_log(
                task_id=task_id,
                message=f"Execution error: {error_msg}",
                level="error",
                agent_name=agent_name,
            )
            return TaskResult(task_id=task_id, success=False, error=error_msg)

    def _build_prompt(self, task: dict, agent_def: AgentDefinition) -> str:
        """Build the full prompt for the implementer, combining agent system prompt and task details."""
        parts = [
            agent_def.system_prompt,
            "",
            "---",
            "",
            f"## Task: {task['title']}",
            "",
            task.get("description", ""),
            "",
            f"**Project path:** {self.project_config.repo_path}",
            f"**Language:** {self.project_config.structure.language}",
        ]
        if self.project_config.structure.framework:
            parts.append(f"**Framework:** {self.project_config.structure.framework}")
        if self.project_config.structure.test_runner:
            parts.append(f"**Test runner:** {self.project_config.structure.test_runner}")

        return "\n".join(parts)

    def _get_implementer(self, name: str) -> BaseImplementer:
        if name not in self._implementers:
            self._implementers[name] = get_implementer(name)
        return self._implementers[name]

    async def cleanup(self) -> None:
        """Close resources."""
        await self.state.close()
