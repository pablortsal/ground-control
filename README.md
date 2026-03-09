# Ground Control

AI agent orchestration system for software projects. Define a team of AI agents, point them at your tickets, and let them plan and implement the work -- from task decomposition to code generation.

## How It Works

```
Tickets (YAML) ──► Planner (LLM) ──► Task Queue ──► Agents ──► Implementers (Cursor CLI / Claude Code)
                                          │
                                     SQLite State
```

1. **Define agents** as Markdown files with YAML frontmatter (role, LLM provider, capabilities, system prompt)
2. **Configure a project** with a YAML file (repo path, language, framework, ticket source, which agents to use)
3. **Write tickets** as local YAML files describing what needs to be built
4. **Run the orchestrator** -- it uses an LLM to decompose tickets into atomic tasks, assigns them to agents, and executes them in parallel via Cursor CLI or Claude Code

## Quick Start

```bash
# Install
pip install -e .

# Set up API keys
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY or OPENAI_API_KEY

# List available agents
gctl agents list

# Create a project config in projects/my-project.yaml
# Point it to your external project repo and tickets directory

# Validate your setup
gctl check my-project

# Run orchestration
gctl run my-project

# Check status
gctl status my-project
```

## Project Structure

```
ground-control/
  ground_control/
    cli.py                  # CLI (Typer)
    orchestrator.py         # Main orchestration engine
    planner.py              # LLM-powered task decomposition
    task_queue.py           # Parallel execution with asyncio
    agent_manager.py        # Loads agent definitions from .md files
    config.py               # Project config loading + validation (Pydantic)
    state.py                # SQLite persistence (runs, tasks, logs)
    llm/                    # LLM provider abstraction
      anthropic.py          # Anthropic (Claude) provider
      openai.py             # OpenAI provider
    implementers/           # Code-writing tool wrappers
      cursor_cli.py         # Cursor CLI wrapper
      claude_code.py        # Claude Code wrapper
    ticket_sources/         # Ticket source abstraction
      local_yaml.py         # Local YAML files
  agents/                   # Agent definitions (ships with CLI)
  projects/                 # Project configuration registry
  tests/                    # Integration tests
```

## Agent Definition Example

```markdown
---
name: developer
role: "Senior Software Developer"
capabilities:
  - write_code
  - run_tests
  - fix_bugs
---
# Senior Developer Agent

You are a senior Software Developer. Your job is to implement
technical tasks by writing high-quality, well-tested code.

## Guidelines
- Follow the project's coding standards
- Write tests for all new features
- Handle edge cases and errors gracefully
```

**Note**: The `implementer` field is optional in agent definitions. It's usually better to specify it at the **project level** for flexibility.

## Project Configuration Example

```yaml
name: my-project
repo_path: /path/to/your/external/project  # Absolute path to external project repo
structure:
  language: typescript
  framework: next.js
  test_runner: vitest
ticket_source:
  type: local_yaml
  path: /path/to/your/external/project/tickets/  # Tickets live in your project repo
agents:
  - developer
  - reviewer
settings:
  max_parallel_agents: 3
  implementer: cursor_cli  # or claude_code (project-level control)
  llm_provider: anthropic   # LLM provider for all agents
  llm_model: claude-sonnet-4-20250514  # Specific model (optional)
```

**Settings Priority**: All infrastructure settings (LLM provider, model, implementer) are defined at the project level. This allows the same agents to work across different projects with different tools and models.

## Ticket Definition Example

Tickets are YAML files stored in your external project repository. Each ticket describes a feature or task to be implemented.

```yaml
id: TICKET-001
title: "Add user authentication endpoint"
description: |
  Create a POST /auth/login endpoint that accepts email and password
  and returns a JWT token on successful authentication.
priority: high
status: open
labels:
  - backend
  - auth
acceptance_criteria:
  - Endpoint returns JWT token on success
  - Returns 401 on invalid credentials
  - Password is validated securely
  - Rate limiting is applied
dependencies: []
```

**Ticket Fields**:
- `id`: Unique identifier (required)
- `title`: Short description (required)
- `description`: Detailed explanation of what needs to be done
- `priority`: `high`, `medium`, or `low`
- `status`: `open`, `in_progress`, `done`, or `blocked`
- `labels`: Tags for categorization
- `acceptance_criteria`: List of testable conditions for completion
- `dependencies`: List of ticket IDs this depends on

Place tickets in your project's ticket directory (e.g., `/path/to/your/project/tickets/TICKET-001.yaml`).

## CLI Commands


| Command                       | Description                                  |
| ----------------------------- | -------------------------------------------- |
| `gctl check <project>`        | Validate setup (API keys, CLI tools, config) |
| `gctl run <project>`          | Run orchestration for a project              |
| `gctl status <project>`       | Show run/task status                         |
| `gctl clean`                  | Delete database and reset run history        |
| `gctl agents list`            | List available agents                        |
| `gctl tickets list <project>` | List project tickets                         |
| `gctl version`                | Show version                                 |


## Requirements

- Python >= 3.10
- API keys for your chosen LLM provider (set via `.env` file or environment variables):
  - `ANTHROPIC_API_KEY` for Claude models
  - `OPENAI_API_KEY` for GPT models
- Cursor CLI and/or Claude Code CLI installed for code implementation

## Configuration

Create a `.env` file in the ground-control directory:

```bash
# Copy the example
cp .env.example .env

# Edit and add your keys
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

The system will automatically load this file when running commands.

## Roadmap

- Web dashboard with real-time status (WebSockets)
- MCP integrations (Jira, Linear, GitHub Issues)
- Agent-to-agent communication
- Automated PR review agent
- Metrics and analytics

