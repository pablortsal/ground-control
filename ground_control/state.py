"""SQLite-backed state persistence for runs, tasks, and logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    config_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    ticket_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    assigned_agent TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    dependencies TEXT NOT NULL DEFAULT '[]',
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    agent_name TEXT,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    run_id TEXT NOT NULL REFERENCES runs(id),
    agent_name TEXT NOT NULL,
    implementer TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    input_prompt TEXT,
    output TEXT,
    error TEXT,
    tokens_used TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_run_id ON tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_executions_run_id ON agent_executions(run_id);
"""


class RunStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """Async SQLite state store for ground-control."""

    def __init__(self, db_path: str | Path = "ground_control.db"):
        self.db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("StateStore not initialized. Call initialize() first.")
        return self._db

    # ── Runs ──────────────────────────────────────────────────────────

    async def create_run(
        self, run_id: str, project_name: str, config_snapshot: dict | None = None
    ) -> dict:
        now = _now()
        config_json = json.dumps(config_snapshot) if config_snapshot else None
        await self.db.execute(
            "INSERT INTO runs (id, project_name, status, created_at, updated_at, config_snapshot) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, project_name, RunStatus.PENDING.value, now, now, config_json),
        )
        await self.db.commit()
        return {
            "id": run_id,
            "project_name": project_name,
            "status": RunStatus.PENDING.value,
            "created_at": now,
        }

    async def update_run_status(self, run_id: str, status: RunStatus) -> None:
        await self.db.execute(
            "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, _now(), run_id),
        )
        await self.db.commit()

    async def get_run(self, run_id: str) -> dict | None:
        async with self.db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_runs(self, project_name: str | None = None, limit: int = 20) -> list[dict]:
        if project_name:
            query = "SELECT * FROM runs WHERE project_name = ? ORDER BY created_at DESC LIMIT ?"
            params = (project_name, limit)
        else:
            query = "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ── Tasks ─────────────────────────────────────────────────────────

    async def create_task(
        self,
        task_id: str,
        run_id: str,
        title: str,
        description: str = "",
        ticket_id: str | None = None,
        assigned_agent: str | None = None,
        priority: int = 0,
        dependencies: list[str] | None = None,
    ) -> dict:
        now = _now()
        deps_json = json.dumps(dependencies or [])
        await self.db.execute(
            "INSERT INTO tasks "
            "(id, run_id, ticket_id, title, description, assigned_agent, status, priority, "
            "dependencies, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id, run_id, ticket_id, title, description,
                assigned_agent, TaskStatus.PENDING.value, priority,
                deps_json, now, now,
            ),
        )
        await self.db.commit()
        return {"id": task_id, "run_id": run_id, "title": title, "status": TaskStatus.PENDING.value}

    async def update_task_status(self, task_id: str, status: TaskStatus, result: str | None = None) -> None:
        if result is not None:
            await self.db.execute(
                "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                (status.value, result, _now(), task_id),
            )
        else:
            await self.db.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, _now(), task_id),
            )
        await self.db.commit()

    async def get_task(self, task_id: str) -> dict | None:
        async with self.db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d["dependencies"] = json.loads(d["dependencies"])
                return d
            return None

    async def list_tasks(self, run_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM tasks WHERE run_id = ? ORDER BY priority DESC, created_at",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["dependencies"] = json.loads(d["dependencies"])
                result.append(d)
            return result

    async def get_pending_tasks(self, run_id: str) -> list[dict]:
        """Get tasks that are ready to run (pending with all dependencies completed)."""
        all_tasks = await self.list_tasks(run_id)
        completed_ids = {t["id"] for t in all_tasks if t["status"] == TaskStatus.COMPLETED.value}

        ready = []
        for task in all_tasks:
            if task["status"] != TaskStatus.PENDING.value:
                continue
            deps = task["dependencies"]
            if all(dep in completed_ids for dep in deps):
                ready.append(task)
        return ready

    # ── Task Logs ─────────────────────────────────────────────────────

    async def add_log(
        self,
        task_id: str,
        message: str,
        level: str = "info",
        agent_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        meta_json = json.dumps(metadata) if metadata else None
        await self.db.execute(
            "INSERT INTO task_logs (task_id, agent_name, level, message, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, agent_name, level, message, meta_json, _now()),
        )
        await self.db.commit()

    async def get_logs(self, task_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM task_logs WHERE task_id = ? ORDER BY created_at", (task_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("metadata"):
                    d["metadata"] = json.loads(d["metadata"])
                result.append(d)
            return result

    # ── Agent Executions ──────────────────────────────────────────────

    async def create_execution(
        self,
        task_id: str,
        run_id: str,
        agent_name: str,
        implementer: str | None = None,
        input_prompt: str | None = None,
    ) -> int:
        now = _now()
        cursor = await self.db.execute(
            "INSERT INTO agent_executions "
            "(task_id, run_id, agent_name, implementer, status, input_prompt, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, run_id, agent_name, implementer, "running", input_prompt, now),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def finish_execution(
        self,
        execution_id: int,
        status: str,
        output: str | None = None,
        error: str | None = None,
        tokens_used: dict | None = None,
    ) -> None:
        tokens_json = json.dumps(tokens_used) if tokens_used else None
        await self.db.execute(
            "UPDATE agent_executions SET status = ?, output = ?, error = ?, "
            "tokens_used = ?, finished_at = ? WHERE id = ?",
            (status, output, error, tokens_json, _now(), execution_id),
        )
        await self.db.commit()

    # ── Summary ───────────────────────────────────────────────────────

    async def get_run_summary(self, run_id: str) -> dict:
        """Get a summary of task statuses for a run."""
        run = await self.get_run(run_id)
        tasks = await self.list_tasks(run_id)

        status_counts: dict[str, int] = {}
        for t in tasks:
            s = t["status"]
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "run": run,
            "total_tasks": len(tasks),
            "status_counts": status_counts,
            "tasks": tasks,
        }
