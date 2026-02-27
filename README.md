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

# Initialize a workspace
gctl init my-workspace
cd my-workspace

# List default agents
gctl agents list

# Create a project config in projects/my-project.yaml
# Add tickets to tickets/my-project/

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
  agents/                   # Agent definitions (.md with YAML frontmatter)
  projects/                 # Project configurations
  tests/                    # Integration tests
```

## Agent Definition Example

```markdown
---
name: developer
role: "Senior Software Developer"
llm_provider: anthropic
llm_model: claude-sonnet-4-20250514
implementer: claude_code
capabilities:
  - write_code
  - run_tests
  - fix_bugs
---
# Senior Developer Agent

You are a senior Software Developer. Your job is to implement
technical tasks by writing high-quality, well-tested code.
```

## Project Configuration Example

```yaml
name: my-project
repo_path: /path/to/repo
structure:
  language: typescript
  framework: next.js
  test_runner: vitest
ticket_source:
  type: local_yaml
  path: ./tickets/my-project/
agents:
  - developer
  - reviewer
settings:
  max_parallel_agents: 3
  implementer: claude_code
  default_llm: anthropic
```

## CLI Commands

| Command | Description |
|---|---|
| `gctl init [path]` | Initialize a ground-control workspace |
| `gctl run <project>` | Run orchestration for a project |
| `gctl status <project>` | Show run/task status |
| `gctl agents list` | List available agents |
| `gctl tickets list <project>` | List project tickets |
| `gctl version` | Show version |

## Requirements

- Python >= 3.10
- API keys for your chosen LLM provider (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`)
- Cursor CLI and/or Claude Code CLI installed for code implementation

## Roadmap

- [ ] Web dashboard with real-time status (WebSockets)
- [ ] MCP integrations (Jira, Linear, GitHub Issues)
- [ ] Agent-to-agent communication
- [ ] Automated PR review agent
- [ ] Metrics and analytics
