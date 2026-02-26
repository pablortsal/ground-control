"""Project configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class TicketSourceConfig(BaseModel):
    type: str = "local_yaml"
    path: str = "./tickets/"


class ProjectSettings(BaseModel):
    max_parallel_agents: int = Field(default=3, ge=1, le=20)
    implementer: str = "claude_code"
    default_llm: str = "anthropic"


class ProjectStructure(BaseModel):
    language: str = "python"
    framework: str | None = None
    test_runner: str | None = None


class ProjectConfig(BaseModel):
    """Full configuration for a managed project."""

    name: str
    repo_path: str
    structure: ProjectStructure = Field(default_factory=ProjectStructure)
    ticket_source: TicketSourceConfig = Field(default_factory=TicketSourceConfig)
    agents: list[str] = Field(default_factory=lambda: ["developer", "reviewer"])
    settings: ProjectSettings = Field(default_factory=ProjectSettings)

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v: str) -> str:
        path = Path(v).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Repository path does not exist: {path}")
        return str(path)


class GroundControlConfig(BaseModel):
    """Top-level ground-control configuration."""

    agents_dir: str = "./agents"
    projects_dir: str = "./projects"
    db_path: str = "./ground_control.db"


def load_project_config(path: str | Path) -> ProjectConfig:
    """Load and validate a project config from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project config not found: {path}")

    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f)

    return ProjectConfig(**data)


def load_gc_config(base_dir: str | Path | None = None) -> GroundControlConfig:
    """Load ground-control's own config, or return defaults."""
    if base_dir is None:
        base_dir = Path.cwd()
    base_dir = Path(base_dir)

    config_path = base_dir / "gc.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return GroundControlConfig(**data)

    return GroundControlConfig()


def find_project_config(project_name: str, projects_dir: str | Path) -> Path:
    """Find a project config file by name in the projects directory."""
    projects_dir = Path(projects_dir)
    candidates = [
        projects_dir / f"{project_name}.yaml",
        projects_dir / f"{project_name}.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No config found for project '{project_name}' in {projects_dir}. "
        f"Looked for: {[str(c) for c in candidates]}"
    )
