"""End-to-end integration tests for Ground Control."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from ground_control.agent_manager import AgentManager, create_default_agents
from ground_control.config import load_project_config, ProjectConfig, load_gc_config
from ground_control.state import StateStore, RunStatus, TaskStatus
from ground_control.ticket_sources.local_yaml import LocalYAMLTicketSource
from ground_control.ticket_sources.base import TicketStatus, TicketPriority
from ground_control.planner import PlannedTask
from ground_control.task_queue import TaskQueue, TaskResult


@pytest.fixture
def workspace(tmp_path):
    """Create a full ground-control workspace for testing."""
    agents_dir = tmp_path / "agents"
    projects_dir = tmp_path / "projects"
    tickets_dir = tmp_path / "tickets"

    agents_dir.mkdir()
    projects_dir.mkdir()
    tickets_dir.mkdir()

    create_default_agents(agents_dir)

    # Create a fake repo path
    repo_dir = tmp_path / "fake-repo"
    repo_dir.mkdir()

    project_config = {
        "name": "test-project",
        "repo_path": str(repo_dir),
        "structure": {
            "language": "python",
            "framework": "fastapi",
            "test_runner": "pytest",
        },
        "ticket_source": {
            "type": "local_yaml",
            "path": str(tickets_dir),
        },
        "agents": ["developer", "reviewer"],
        "settings": {
            "max_parallel_agents": 2,
            "implementer": "claude_code",
            "default_llm": "anthropic",
        },
    }

    project_file = projects_dir / "test-project.yaml"
    with open(project_file, "w") as f:
        yaml.dump(project_config, f, default_flow_style=False)

    sample_tickets = [
        {
            "id": "TICKET-001",
            "title": "Add user authentication endpoint",
            "description": "Create a POST /auth/login endpoint that accepts email and password",
            "priority": "high",
            "status": "open",
            "labels": ["backend", "auth"],
            "acceptance_criteria": [
                "Endpoint returns JWT token on success",
                "Returns 401 on invalid credentials",
            ],
        },
        {
            "id": "TICKET-002",
            "title": "Add health check endpoint",
            "description": "Create a GET /health endpoint that returns service status",
            "priority": "low",
            "status": "open",
            "labels": ["backend", "ops"],
            "acceptance_criteria": [
                "Returns 200 with JSON body",
                "Includes uptime and version info",
            ],
        },
        {
            "id": "TICKET-003",
            "title": "Already done ticket",
            "description": "This ticket is already completed",
            "priority": "medium",
            "status": "done",
        },
    ]

    tickets_file = tickets_dir / "tickets.yaml"
    with open(tickets_file, "w") as f:
        yaml.dump(sample_tickets, f, default_flow_style=False)

    gc_config = {
        "agents_dir": str(agents_dir),
        "projects_dir": str(projects_dir),
        "db_path": str(tmp_path / "test.db"),
    }
    gc_yaml = tmp_path / "gc.yaml"
    with open(gc_yaml, "w") as f:
        yaml.dump(gc_config, f)

    return tmp_path


class TestAgentManager:
    def test_load_default_agents(self, workspace):
        manager = AgentManager(workspace / "agents")
        agents = manager.load_all()

        assert len(agents) == 4
        assert "developer" in agents
        assert "reviewer" in agents
        assert "architect" in agents
        assert "product-manager" in agents

    def test_get_agent(self, workspace):
        manager = AgentManager(workspace / "agents")
        manager.load_all()

        dev = manager.get("developer")
        assert dev.name == "developer"
        assert dev.role == "Senior Software Developer"
        assert dev.llm_provider == "anthropic"
        assert dev.implementer == "claude_code"
        assert "write_code" in dev.capabilities
        assert len(dev.system_prompt) > 0

    def test_get_missing_agent_raises(self, workspace):
        manager = AgentManager(workspace / "agents")
        manager.load_all()

        with pytest.raises(KeyError, match="nonexistent"):
            manager.get("nonexistent")


class TestProjectConfig:
    def test_load_project_config(self, workspace):
        config = load_project_config(workspace / "projects" / "test-project.yaml")

        assert config.name == "test-project"
        assert config.structure.language == "python"
        assert config.structure.framework == "fastapi"
        assert config.ticket_source.type == "local_yaml"
        assert config.settings.max_parallel_agents == 2
        assert "developer" in config.agents

    def test_missing_config_raises(self, workspace):
        with pytest.raises(FileNotFoundError):
            load_project_config(workspace / "projects" / "nonexistent.yaml")


class TestTicketSource:
    @pytest.mark.asyncio
    async def test_load_tickets(self, workspace):
        config = load_project_config(workspace / "projects" / "test-project.yaml")
        source = LocalYAMLTicketSource(config.ticket_source.path)

        tickets = await source.load_tickets()
        assert len(tickets) == 3

        open_tickets = [t for t in tickets if t.status == TicketStatus.OPEN]
        assert len(open_tickets) == 2

    @pytest.mark.asyncio
    async def test_get_ticket(self, workspace):
        config = load_project_config(workspace / "projects" / "test-project.yaml")
        source = LocalYAMLTicketSource(config.ticket_source.path)

        ticket = await source.get_ticket("TICKET-001")
        assert ticket is not None
        assert ticket.title == "Add user authentication endpoint"
        assert ticket.priority == TicketPriority.HIGH

    @pytest.mark.asyncio
    async def test_update_ticket_status(self, workspace):
        config = load_project_config(workspace / "projects" / "test-project.yaml")
        source = LocalYAMLTicketSource(config.ticket_source.path)

        await source.update_ticket_status("TICKET-001", TicketStatus.IN_PROGRESS)

        ticket = await source.get_ticket("TICKET-001")
        assert ticket.status == TicketStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        source = LocalYAMLTicketSource(empty_dir)
        tickets = await source.load_tickets()
        assert tickets == []


class TestStateStore:
    @pytest.mark.asyncio
    async def test_create_and_get_run(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        run = await state.create_run("run-001", "test-project")
        assert run["id"] == "run-001"
        assert run["status"] == "pending"

        fetched = await state.get_run("run-001")
        assert fetched is not None
        assert fetched["project_name"] == "test-project"

        await state.close()

    @pytest.mark.asyncio
    async def test_task_lifecycle(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        await state.create_run("run-001", "test-project")

        task = await state.create_task(
            task_id="task-001",
            run_id="run-001",
            title="Implement login",
            description="Create login endpoint",
            assigned_agent="developer",
            priority=5,
        )
        assert task["status"] == "pending"

        await state.update_task_status("task-001", TaskStatus.RUNNING)
        fetched = await state.get_task("task-001")
        assert fetched["status"] == "running"

        await state.update_task_status("task-001", TaskStatus.COMPLETED, result="Done")
        fetched = await state.get_task("task-001")
        assert fetched["status"] == "completed"
        assert fetched["result"] == "Done"

        await state.close()

    @pytest.mark.asyncio
    async def test_dependency_resolution(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        await state.create_run("run-001", "test-project")

        await state.create_task("task-a", "run-001", "Task A")
        await state.create_task("task-b", "run-001", "Task B", dependencies=["task-a"])
        await state.create_task("task-c", "run-001", "Task C")

        pending = await state.get_pending_tasks("run-001")
        pending_ids = {t["id"] for t in pending}
        assert "task-a" in pending_ids
        assert "task-c" in pending_ids
        assert "task-b" not in pending_ids  # blocked by task-a

        await state.update_task_status("task-a", TaskStatus.COMPLETED)
        pending = await state.get_pending_tasks("run-001")
        pending_ids = {t["id"] for t in pending}
        assert "task-b" in pending_ids  # now unblocked

        await state.close()

    @pytest.mark.asyncio
    async def test_run_summary(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        await state.create_run("run-001", "test-project")
        await state.create_task("task-1", "run-001", "Task 1")
        await state.create_task("task-2", "run-001", "Task 2")
        await state.update_task_status("task-1", TaskStatus.COMPLETED)

        summary = await state.get_run_summary("run-001")
        assert summary["total_tasks"] == 2
        assert summary["status_counts"]["completed"] == 1
        assert summary["status_counts"]["pending"] == 1

        await state.close()

    @pytest.mark.asyncio
    async def test_logging(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        await state.create_run("run-001", "test-project")
        await state.create_task("task-1", "run-001", "Task 1")

        await state.add_log("task-1", "Starting work", agent_name="developer")
        await state.add_log("task-1", "Completed", level="info", metadata={"files": 3})

        logs = await state.get_logs("task-1")
        assert len(logs) == 2
        assert logs[0]["message"] == "Starting work"
        assert logs[1]["metadata"]["files"] == 3

        await state.close()


class TestTaskQueue:
    @pytest.mark.asyncio
    async def test_parallel_execution(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        await state.create_run("run-001", "test-project")
        await state.create_task("task-1", "run-001", "Task 1", priority=5)
        await state.create_task("task-2", "run-001", "Task 2", priority=3)
        await state.create_task("task-3", "run-001", "Task 3", priority=1)

        execution_order = []

        async def mock_executor(task: dict) -> TaskResult:
            execution_order.append(task["id"])
            await asyncio.sleep(0.05)
            return TaskResult(task_id=task["id"], success=True, output="ok")

        queue = TaskQueue(state=state, max_parallel=2)
        results = await queue.execute_all("run-001", mock_executor)

        assert len(results) == 3
        assert all(r.success for r in results)

        for task_id in ["task-1", "task-2", "task-3"]:
            task = await state.get_task(task_id)
            assert task["status"] == "completed"

        await state.close()

    @pytest.mark.asyncio
    async def test_execution_with_dependencies(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        await state.create_run("run-001", "test-project")
        await state.create_task("task-a", "run-001", "Task A")
        await state.create_task("task-b", "run-001", "Task B", dependencies=["task-a"])

        execution_order = []

        async def mock_executor(task: dict) -> TaskResult:
            execution_order.append(task["id"])
            return TaskResult(task_id=task["id"], success=True, output="ok")

        queue = TaskQueue(state=state, max_parallel=2)
        results = await queue.execute_all("run-001", mock_executor)

        assert len(results) == 2
        assert execution_order.index("task-a") < execution_order.index("task-b")

        await state.close()

    @pytest.mark.asyncio
    async def test_failed_task(self, tmp_path):
        state = StateStore(tmp_path / "test.db")
        await state.initialize()

        await state.create_run("run-001", "test-project")
        await state.create_task("task-1", "run-001", "Failing Task")

        async def failing_executor(task: dict) -> TaskResult:
            return TaskResult(task_id=task["id"], success=False, error="Something went wrong")

        queue = TaskQueue(state=state, max_parallel=2)
        results = await queue.execute_all("run-001", failing_executor)

        assert len(results) == 1
        assert not results[0].success
        assert results[0].error == "Something went wrong"

        task = await state.get_task("task-1")
        assert task["status"] == "failed"

        await state.close()
