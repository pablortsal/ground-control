"""Ground Control CLI - main entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ground_control import __version__

app = typer.Typer(
    name="gc",
    help="Ground Control - AI Agent Orchestration System",
    no_args_is_help=True,
)
agents_app = typer.Typer(help="Manage agent definitions")
tickets_app = typer.Typer(help="Manage project tickets")
app.add_typer(agents_app, name="agents")
app.add_typer(tickets_app, name="tickets")

console = Console()


def _run_async(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)


# ── Top-level commands ────────────────────────────────────────────────


@app.command()
def init(
    path: str = typer.Argument(".", help="Directory to initialize ground-control in"),
):
    """Initialize a new ground-control workspace."""
    from ground_control.agent_manager import create_default_agents

    base = Path(path).resolve()
    base.mkdir(parents=True, exist_ok=True)

    dirs = ["agents", "projects", "tickets"]
    for d in dirs:
        (base / d).mkdir(exist_ok=True)

    create_default_agents(base / "agents")

    gc_yaml = base / "gc.yaml"
    if not gc_yaml.exists():
        gc_yaml.write_text(
            "agents_dir: ./agents\n"
            "projects_dir: ./projects\n"
            "db_path: ./ground_control.db\n"
        )

    console.print(Panel(
        f"[bold green]Workspace initialized at:[/] {base}\n\n"
        f"  [dim]agents/[/]     - Agent definitions (4 defaults created)\n"
        f"  [dim]projects/[/]   - Project configurations\n"
        f"  [dim]tickets/[/]    - Local ticket files\n"
        f"  [dim]gc.yaml[/]     - Ground Control config\n\n"
        f"Next steps:\n"
        f"  1. Create a project config in [bold]projects/[/]\n"
        f"  2. Add tickets to [bold]tickets/[/]\n"
        f"  3. Run [bold cyan]gc run <project>[/]",
        title="[bold cyan]Ground Control[/]",
        border_style="cyan",
    ))


@app.command()
def run(
    project: str = typer.Argument(..., help="Project name to run"),
    base_dir: str = typer.Option(".", "--base-dir", "-d", help="Ground-control workspace directory"),
):
    """Execute an orchestration run for a project."""
    async def _run():
        from ground_control.orchestrator import Orchestrator

        orchestrator = await Orchestrator.from_project_name(project, base_dir)
        try:
            run_id = await orchestrator.run()
            console.print(f"\n[dim]Run ID: {run_id}[/]")
            console.print("[dim]View details with: gc status {project}[/]")
        finally:
            await orchestrator.cleanup()

    _run_async(_run())


@app.command()
def status(
    project: str = typer.Argument(..., help="Project name"),
    run_id: str = typer.Option(None, "--run-id", "-r", help="Specific run ID (defaults to latest)"),
    base_dir: str = typer.Option(".", "--base-dir", "-d", help="Ground-control workspace directory"),
):
    """Show the status of a project's runs and tasks."""
    async def _status():
        from ground_control.config import load_gc_config
        from ground_control.state import StateStore

        base = Path(base_dir).resolve()
        gc_config = load_gc_config(base)
        state = StateStore(base / gc_config.db_path)
        await state.initialize()

        try:
            if run_id:
                summary = await state.get_run_summary(run_id)
            else:
                runs = await state.list_runs(project_name=project, limit=1)
                if not runs:
                    console.print(f"[yellow]No runs found for project '{project}'[/]")
                    return
                summary = await state.get_run_summary(runs[0]["id"])

            run_info = summary["run"]
            if not run_info:
                console.print("[yellow]Run not found[/]")
                return

            status_color = {
                "pending": "dim",
                "planning": "yellow",
                "running": "blue",
                "completed": "green",
                "failed": "red",
            }.get(run_info["status"], "white")

            console.print(Panel(
                f"[bold]Run:[/] {run_info['id']}\n"
                f"[bold]Project:[/] {run_info['project_name']}\n"
                f"[bold]Status:[/] [{status_color}]{run_info['status']}[/{status_color}]\n"
                f"[bold]Created:[/] {run_info['created_at']}\n"
                f"[bold]Tasks:[/] {summary['total_tasks']}",
                title="[bold cyan]Run Status[/]",
                border_style="cyan",
            ))

            if summary["status_counts"]:
                counts_table = Table(title="Task Summary")
                counts_table.add_column("Status", style="bold")
                counts_table.add_column("Count", justify="right")
                for s, count in sorted(summary["status_counts"].items()):
                    counts_table.add_row(s, str(count))
                console.print(counts_table)

            if summary["tasks"]:
                tasks_table = Table(title="Tasks")
                tasks_table.add_column("ID", style="dim", max_width=20)
                tasks_table.add_column("Title")
                tasks_table.add_column("Agent", style="cyan")
                tasks_table.add_column("Status")

                status_styles = {
                    "pending": "dim",
                    "queued": "yellow",
                    "running": "blue",
                    "completed": "green",
                    "failed": "red",
                    "skipped": "dim",
                }

                for task in summary["tasks"]:
                    ts = task["status"]
                    style = status_styles.get(ts, "white")
                    tasks_table.add_row(
                        task["id"],
                        task["title"],
                        task.get("assigned_agent", "-"),
                        f"[{style}]{ts}[/{style}]",
                    )
                console.print(tasks_table)

        finally:
            await state.close()

    _run_async(_status())


@app.command()
def version():
    """Show Ground Control version."""
    console.print(f"[bold cyan]Ground Control[/] v{__version__}")


# ── Agents subcommands ────────────────────────────────────────────────


@agents_app.command("list")
def agents_list(
    base_dir: str = typer.Option(".", "--base-dir", "-d", help="Ground-control workspace directory"),
):
    """List all available agent definitions."""
    from ground_control.agent_manager import AgentManager
    from ground_control.config import load_gc_config

    base = Path(base_dir).resolve()
    gc_config = load_gc_config(base)
    manager = AgentManager(base / gc_config.agents_dir)

    try:
        agents = manager.load_all()
    except FileNotFoundError:
        console.print("[red]Agents directory not found. Run 'gc init' first.[/]")
        raise typer.Exit(1)

    if not agents:
        console.print("[yellow]No agents found.[/]")
        return

    table = Table(title="Available Agents")
    table.add_column("Name", style="bold cyan")
    table.add_column("Role")
    table.add_column("LLM Provider")
    table.add_column("Implementer")
    table.add_column("Capabilities")

    for agent in agents.values():
        table.add_row(
            agent.name,
            agent.role,
            f"{agent.llm_provider}" + (f" ({agent.llm_model})" if agent.llm_model else ""),
            agent.implementer or "-",
            ", ".join(agent.capabilities) if agent.capabilities else "-",
        )

    console.print(table)


# ── Tickets subcommands ───────────────────────────────────────────────


@tickets_app.command("list")
def tickets_list(
    project: str = typer.Argument(..., help="Project name"),
    base_dir: str = typer.Option(".", "--base-dir", "-d", help="Ground-control workspace directory"),
):
    """List tickets for a project."""
    async def _list():
        from ground_control.config import load_gc_config, find_project_config, load_project_config
        from ground_control.ticket_sources import get_ticket_source

        base = Path(base_dir).resolve()
        gc_config = load_gc_config(base)

        try:
            project_path = find_project_config(project, base / gc_config.projects_dir)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1)

        project_config = load_project_config(project_path)
        source = get_ticket_source(
            project_config.ticket_source.type,
            path=project_config.ticket_source.path,
        )

        tickets = await source.load_tickets()

        if not tickets:
            console.print(f"[yellow]No tickets found for project '{project}'[/]")
            return

        table = Table(title=f"Tickets - {project}")
        table.add_column("ID", style="bold")
        table.add_column("Title")
        table.add_column("Priority")
        table.add_column("Status")
        table.add_column("Labels")

        priority_styles = {"high": "red", "medium": "yellow", "low": "green"}
        status_styles = {"open": "cyan", "in_progress": "blue", "done": "green", "blocked": "red"}

        for ticket in tickets:
            p_style = priority_styles.get(ticket.priority.value, "white")
            s_style = status_styles.get(ticket.status.value, "white")
            table.add_row(
                ticket.id,
                ticket.title,
                f"[{p_style}]{ticket.priority.value}[/{p_style}]",
                f"[{s_style}]{ticket.status.value}[/{s_style}]",
                ", ".join(ticket.labels) if ticket.labels else "-",
            )

        console.print(table)

    _run_async(_list())


if __name__ == "__main__":
    app()
