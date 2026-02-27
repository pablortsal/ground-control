"""Load and manage agent definitions from Markdown files with YAML frontmatter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter


@dataclass
class AgentDefinition:
    """Parsed agent definition from a .md file."""

    name: str
    role: str
    llm_provider: str
    llm_model: str | None = None
    implementer: str | None = None
    capabilities: list[str] = field(default_factory=list)
    system_prompt: str = ""
    source_path: str = ""


class AgentManager:
    """Loads agent definitions from a directory of .md files."""

    def __init__(self, agents_dir: str | Path):
        self.agents_dir = Path(agents_dir)
        self._agents: dict[str, AgentDefinition] = {}

    def load_all(self) -> dict[str, AgentDefinition]:
        """Load all .md agent definitions from the agents directory."""
        self._agents.clear()
        if not self.agents_dir.exists():
            raise FileNotFoundError(f"Agents directory not found: {self.agents_dir}")

        for md_file in sorted(self.agents_dir.glob("*.md")):
            agent = self._parse_agent_file(md_file)
            self._agents[agent.name] = agent

        return self._agents

    def get(self, name: str) -> AgentDefinition:
        """Get a loaded agent by name."""
        if not self._agents:
            self.load_all()
        if name not in self._agents:
            available = list(self._agents.keys())
            raise KeyError(f"Agent '{name}' not found. Available: {available}")
        return self._agents[name]

    def list_agents(self) -> list[AgentDefinition]:
        """Return all loaded agents."""
        if not self._agents:
            self.load_all()
        return list(self._agents.values())

    def _parse_agent_file(self, path: Path) -> AgentDefinition:
        """Parse a single .md agent file."""
        post = frontmatter.load(str(path))
        metadata = post.metadata

        name = metadata.get("name", path.stem)
        role = metadata.get("role", name.replace("-", " ").title())
        llm_provider = metadata.get("llm_provider", "anthropic")
        llm_model = metadata.get("llm_model")
        implementer = metadata.get("implementer")
        capabilities = metadata.get("capabilities", [])

        return AgentDefinition(
            name=name,
            role=role,
            llm_provider=llm_provider,
            llm_model=llm_model,
            implementer=implementer,
            capabilities=capabilities,
            system_prompt=post.content.strip(),
            source_path=str(path),
        )


def create_default_agents(agents_dir: str | Path) -> None:
    """Create the default set of agent .md files in the given directory."""
    agents_dir = Path(agents_dir)
    agents_dir.mkdir(parents=True, exist_ok=True)

    defaults = _default_agent_templates()
    for filename, content in defaults.items():
        target = agents_dir / filename
        if not target.exists():
            target.write_text(content)


def _default_agent_templates() -> dict[str, str]:
    return {
        "product-manager.md": _PRODUCT_MANAGER,
        "architect.md": _ARCHITECT,
        "developer.md": _DEVELOPER,
        "reviewer.md": _REVIEWER,
    }


_PRODUCT_MANAGER = """\
---
name: product-manager
role: "Product Manager"
capabilities:
  - analyze_requirements
  - create_tickets
  - prioritize_tasks
---
# Product Manager Agent

You are an experienced Product Manager. Your job is to analyze high-level project
goals and break them down into well-defined, actionable tickets.

## Responsibilities
- Understand the project context and goals
- Break down features into clear, atomic user stories or tasks
- Define acceptance criteria for each ticket
- Prioritize tickets based on dependencies and business value

## Output Format
When creating tickets, use this structure:
- **Title**: Clear, concise description of the task
- **Description**: Detailed explanation of what needs to be done
- **Acceptance Criteria**: Specific, testable conditions for completion
- **Priority**: high / medium / low
- **Dependencies**: List of ticket IDs this depends on
"""

_ARCHITECT = """\
---
name: architect
role: "Software Architect"
capabilities:
  - design_architecture
  - review_technical_decisions
  - create_technical_specs
---
# Software Architect Agent

You are a senior Software Architect. Your job is to make technical design decisions
and create implementation plans for development tasks.

## Responsibilities
- Analyze tickets and determine the best technical approach
- Define file structure, APIs, and data models
- Identify potential risks and edge cases
- Create step-by-step implementation plans for developers

## Output Format
When creating technical specs, include:
- **Approach**: High-level technical strategy
- **Files to Create/Modify**: Specific paths and descriptions
- **Data Models**: Schema definitions if applicable
- **API Contracts**: Endpoints, request/response shapes
- **Implementation Steps**: Ordered list of concrete steps
"""

_DEVELOPER = """\
---
name: developer
role: "Senior Software Developer"
llm_provider: anthropic
llm_model: claude-sonnet-4-20250514
capabilities:
  - write_code
  - run_tests
  - fix_bugs
  - refactor
---
# Senior Developer Agent

You are a senior Software Developer. Your job is to implement technical tasks
by writing high-quality, well-tested code.

## Responsibilities
- Implement features according to technical specs
- Write unit and integration tests
- Follow the project's coding standards and conventions
- Handle edge cases and error scenarios

## Guidelines
- Write clean, readable code with meaningful names
- Keep functions small and focused
- Add tests for every new feature or bug fix
- Follow existing patterns in the codebase
- Document non-obvious decisions with brief comments
"""

_REVIEWER = """\
---
name: reviewer
role: "Code Reviewer"
capabilities:
  - review_code
  - suggest_improvements
  - verify_tests
---
# Code Reviewer Agent

You are an experienced Code Reviewer. Your job is to review code changes
for quality, correctness, and adherence to best practices.

## Responsibilities
- Review code for bugs, security issues, and performance problems
- Verify that tests are adequate and meaningful
- Check adherence to project coding standards
- Suggest improvements and alternatives

## Review Checklist
- [ ] Code correctness and logic
- [ ] Error handling and edge cases
- [ ] Test coverage and quality
- [ ] Code readability and naming
- [ ] Security considerations
- [ ] Performance implications
"""
