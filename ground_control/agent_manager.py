"""Load and manage agent definitions from Markdown files with YAML frontmatter."""

from __future__ import annotations

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
