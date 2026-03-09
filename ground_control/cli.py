"""Ground Control CLI - main entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ground_control import __version__
from ground_control.env import load_environment

# Load environment variables from .env file at startup
load_environment()

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
def run(
    project: str = typer.Argument(..., help="Project name to run"),
):
    """Execute an orchestration run for a project."""
    async def _run():
        from ground_control.config import get_base_dir, find_project_config, load_project_config
        from ground_control.env import check_required_keys
        from ground_control.implementers import get_implementer
        from ground_control.orchestrator import Orchestrator

        base = get_base_dir()
        project_path = find_project_config(project, base / "projects")
        project_config = load_project_config(project_path)
        
        # Check if API key is set for the LLM provider
        provider = project_config.settings.llm_provider
        key_status = check_required_keys([provider])
        
        if not key_status[provider]:
            console.print(Panel(
                f"[bold red]Error:[/] API key not set for {provider}\n\n"
                f"Please set the [bold]{provider.upper()}_API_KEY[/] environment variable.\n\n"
                f"You can:\n"
                f"  1. Create a [bold].env[/] file in your workspace with:\n"
                f"     [dim]{provider.upper()}_API_KEY=your_key_here[/]\n"
                f"  2. Export it in your shell:\n"
                f"     [dim]export {provider.upper()}_API_KEY=your_key_here[/]",
                title="[bold red]Missing API Key[/]",
                border_style="red",
            ))
            raise typer.Exit(1)
        
        # Check if the implementer CLI is installed
        implementer_name = project_config.settings.implementer
        implementer = get_implementer(implementer_name)
        
        if not await implementer.is_available():
            install_instructions = {
                "cursor_cli": "Install from https://cursor.com or via: brew install cursor (macOS)",
                "claude_code": "Install via: npm install -g @anthropic-ai/claude-code",
            }
            instruction = install_instructions.get(implementer_name, f"Install the {implementer_name} CLI tool")
            
            console.print(Panel(
                f"[bold red]Error:[/] Implementer '{implementer_name}' not found\n\n"
                f"The CLI tool required to write code is not installed.\n\n"
                f"[bold]Installation:[/]\n"
                f"  {instruction}",
                title="[bold red]Missing Implementer[/]",
                border_style="red",
            ))
            raise typer.Exit(1)

        console.print(f"[dim]✓ API key configured for {provider}[/]")
        console.print(f"[dim]✓ Implementer '{implementer_name}' is available[/]\n")

        orchestrator = await Orchestrator.from_project_name(project)
        try:
            run_id = await orchestrator.run()
            console.print(f"\n[dim]Run ID: {run_id}[/]")
            console.print("[dim]View details with: gctl status {project}[/]")
        finally:
            await orchestrator.cleanup()

    _run_async(_run())


@app.command()
def status(
    project: str = typer.Argument(..., help="Project name"),
    run_id: str = typer.Option(None, "--run-id", "-r", help="Specific run ID (defaults to latest)"),
):
    """Show the status of a project's runs and tasks."""
    async def _status():
        from ground_control.config import get_base_dir
        from ground_control.state import StateStore

        base = get_base_dir()
        state = StateStore(base / "ground_control.db")
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


@app.command()
def clean(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Delete the database and reset all run history."""
    from ground_control.config import get_base_dir
    
    base = get_base_dir()
    db_path = base / "ground_control.db"
    
    if not db_path.exists():
        console.print(f"[yellow]No database found at {db_path}[/]")
        return
    
    if not confirm:
        response = typer.confirm(
            f"This will permanently delete all run history in {db_path}. Continue?"
        )
        if not response:
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit(0)
    
    db_path.unlink()
    console.print(f"[green]✓[/] Database deleted: {db_path}")
    console.print("[dim]The database will be recreated automatically on next run.[/]")


@app.command()
def check(
    project: str = typer.Argument(..., help="Project name to check"),
):
    """Check if all requirements are met to run a project."""
    async def _check():
        from ground_control.config import get_base_dir, find_project_config, load_project_config
        from ground_control.env import check_required_keys
        from ground_control.implementers import get_implementer
        from ground_control.agent_manager import AgentManager

        console.print(Panel(
            f"[bold]Checking setup for project:[/] {project}",
            title="[bold cyan]Ground Control - Setup Check[/]",
            border_style="cyan",
        ))

        base = get_base_dir()
        
        checks = []
        
        # Check 1: Project config exists
        try:
            project_path = find_project_config(project, base / "projects")
            project_config = load_project_config(project_path)
            checks.append(("✓", "green", f"Project config found: {project_path.name}"))
        except FileNotFoundError as e:
            checks.append(("✗", "red", f"Project config not found: {e}"))
            console.print("\n".join([f"[{color}]{icon}[/{color}] {msg}" for icon, color, msg in checks]))
            raise typer.Exit(1)
        
        # Check 2: Repo path exists
        repo_path = Path(project_config.repo_path)
        if repo_path.exists():
            checks.append(("✓", "green", f"Repo path exists: {project_config.repo_path}"))
        else:
            checks.append(("✗", "red", f"Repo path not found: {project_config.repo_path}"))
        
        # Check 3: API key
        provider = project_config.settings.llm_provider
        key_status = check_required_keys([provider])
        if key_status[provider]:
            checks.append(("✓", "green", f"API key set for {provider}"))
        else:
            checks.append(("✗", "red", f"API key missing for {provider} (set {provider.upper()}_API_KEY)"))
        
        # Check 4: Implementer CLI
        implementer_name = project_config.settings.implementer
        implementer = get_implementer(implementer_name)
        if await implementer.is_available():
            checks.append(("✓", "green", f"Implementer '{implementer_name}' is installed"))
        else:
            install_instructions = {
                "cursor_cli": "brew install cursor (macOS) or https://cursor.com",
                "claude_code": "npm install -g @anthropic-ai/claude-code",
            }
            instruction = install_instructions.get(implementer_name, "Install required CLI")
            checks.append(("✗", "red", f"Implementer '{implementer_name}' not found ({instruction})"))
        
        # Check 5: Agents
        agent_manager = AgentManager(base / "agents")
        try:
            agent_manager.load_all()
            missing_agents = [a for a in project_config.agents if a not in agent_manager._agents]
            if not missing_agents:
                checks.append(("✓", "green", f"All {len(project_config.agents)} required agents found"))
            else:
                checks.append(("✗", "red", f"Missing agents: {', '.join(missing_agents)}"))
        except FileNotFoundError:
            checks.append(("✗", "red", f"Agents directory not found: {base / 'agents'}"))
        
        # Check 6: Tickets
        ticket_path = Path(project_config.ticket_source.path)
        if not ticket_path.is_absolute():
            ticket_path = base / ticket_path
        
        if ticket_path.exists():
            yaml_files = list(ticket_path.glob("*.yaml")) + list(ticket_path.glob("*.yml"))
            if yaml_files:
                checks.append(("✓", "green", f"Tickets found: {len(yaml_files)} file(s)"))
            else:
                checks.append(("⚠", "yellow", f"Ticket directory exists but empty: {ticket_path}"))
        else:
            checks.append(("⚠", "yellow", f"Ticket directory not found: {ticket_path}"))
        
        # Print all checks
        console.print()
        for icon, color, msg in checks:
            console.print(f"[{color}]{icon}[/{color}] {msg}")
        
        # Summary
        errors = sum(1 for _, color, _ in checks if color == "red")
        warnings = sum(1 for _, color, _ in checks if color == "yellow")
        
        console.print()
        if errors > 0:
            console.print(Panel(
                f"[bold red]{errors} error(s) found.[/] Fix the issues above before running.",
                border_style="red",
            ))
            raise typer.Exit(1)
        elif warnings > 0:
            console.print(Panel(
                f"[bold yellow]{warnings} warning(s) found.[/] You can proceed but may have issues.",
                border_style="yellow",
            ))
        else:
            console.print(Panel(
                "[bold green]All checks passed! ✓[/] Ready to run orchestration.",
                border_style="green",
            ))

    _run_async(_check())


# ── Agents subcommands ────────────────────────────────────────────────


@agents_app.command("list")
def agents_list(
):
    """List all available agent definitions."""
    from ground_control.agent_manager import AgentManager
    from ground_control.config import get_base_dir

    base = get_base_dir()
    manager = AgentManager(base / "agents")

    try:
        agents = manager.load_all()
    except FileNotFoundError:
        console.print("[red]Agents directory not found.[/]")
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
):
    """List tickets for a project."""
    async def _list():
        from ground_control.config import get_base_dir, find_project_config, load_project_config
        from ground_control.ticket_sources import get_ticket_source

        base = get_base_dir()

        try:
            project_path = find_project_config(project, base / "projects")
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
