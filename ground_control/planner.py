"""LLM-powered planner that decomposes tickets into atomic tasks."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from ground_control.agent_manager import AgentDefinition
from ground_control.config import ProjectConfig
from ground_control.llm.base import BaseLLMProvider
from ground_control.ticket_sources.base import Ticket


@dataclass
class PlannedTask:
    """A single atomic task produced by the planner."""

    id: str
    title: str
    description: str
    assigned_agent: str
    priority: int = 0
    dependencies: list[str] = field(default_factory=list)
    ticket_id: str | None = None


PLANNING_SYSTEM_PROMPT = """\
You are a project planning AI. Given a list of tickets and available agents, \
decompose each ticket into atomic, implementable tasks and assign them to the \
most appropriate agent.

Rules:
- Each task must be small enough for a single agent to complete in one session
- Tasks can have dependencies on other tasks (use task IDs)
- Assign each task to exactly one agent based on their capabilities
- Set priority: higher number = higher priority (0-10)
- Return valid JSON only

Available agents and their capabilities:
{agents_description}

Project context:
- Language: {language}
- Framework: {framework}
- Test runner: {test_runner}
"""

PLANNING_USER_PROMPT = """\
Decompose these tickets into atomic tasks:

{tickets_json}

Respond with a JSON object:
{{
  "tasks": [
    {{
      "id": "task-<short-uuid>",
      "title": "Brief task title",
      "description": "Detailed description of what to do",
      "assigned_agent": "<agent-name>",
      "priority": <0-10>,
      "dependencies": ["task-id-1"],
      "ticket_id": "<original-ticket-id>"
    }}
  ]
}}
"""


class Planner:
    """Uses an LLM to decompose tickets into tasks assigned to agents."""

    def __init__(self, llm: BaseLLMProvider, config: ProjectConfig):
        self.llm = llm
        self.config = config

    async def plan(
        self,
        tickets: list[Ticket],
        agents: list[AgentDefinition],
    ) -> list[PlannedTask]:
        if not tickets:
            return []

        agents_desc = self._format_agents(agents)
        tickets_json = self._format_tickets(tickets)

        system = PLANNING_SYSTEM_PROMPT.format(
            agents_description=agents_desc,
            language=self.config.structure.language,
            framework=self.config.structure.framework or "none",
            test_runner=self.config.structure.test_runner or "none",
        )

        user_msg = PLANNING_USER_PROMPT.format(tickets_json=tickets_json)

        result = await self.llm.complete_json(
            messages=[{"role": "user", "content": user_msg}],
            system=system,
            temperature=0.2,
            max_tokens=8192,
        )

        return self._parse_plan(result, tickets)

    def _format_agents(self, agents: list[AgentDefinition]) -> str:
        lines = []
        for a in agents:
            caps = ", ".join(a.capabilities) if a.capabilities else "general"
            lines.append(f"- {a.name} ({a.role}): capabilities=[{caps}]")
        return "\n".join(lines)

    def _format_tickets(self, tickets: list[Ticket]) -> str:
        items = []
        for t in tickets:
            items.append({
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority.value,
                "acceptance_criteria": t.acceptance_criteria,
                "dependencies": t.dependencies,
            })
        return json.dumps(items, indent=2)

    def _parse_plan(self, data: dict, tickets: list[Ticket]) -> list[PlannedTask]:
        raw_tasks = data.get("tasks", [])
        planned: list[PlannedTask] = []

        for raw in raw_tasks:
            task_id = raw.get("id", f"task-{uuid.uuid4().hex[:8]}")
            planned.append(PlannedTask(
                id=task_id,
                title=raw.get("title", "Untitled task"),
                description=raw.get("description", ""),
                assigned_agent=raw.get("assigned_agent", "developer"),
                priority=int(raw.get("priority", 0)),
                dependencies=raw.get("dependencies", []),
                ticket_id=raw.get("ticket_id"),
            ))

        return planned
