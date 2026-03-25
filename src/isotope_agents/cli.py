"""CLI entry point for isotope-agents.

Provides the `isotope` command with `chat`, `run`, and `sessions` subcommands.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import click

from isotope_agents.config import IsotopeConfig
from isotope_agents.presets import PRESETS


@click.group()
@click.version_option(package_name="isotope-agents")
def main() -> None:
    """Isotope — a pluggable Python agent framework."""


@main.command()
@click.option(
    "--preset",
    default=None,
    type=click.Choice(list(PRESETS.keys())),
    help="Preset to use (coding, assistant, minimal)",
)
@click.option("--model", default=None, help="Model to use")
@click.option("--base-url", default=None, help="Provider base URL")
@click.option("--session", "session_id", default=None, help="Resume a saved session by ID")
def chat(
    preset: str | None,
    model: str | None,
    base_url: str | None,
    session_id: str | None,
) -> None:
    """Start interactive TUI chat."""
    from isotope_agents.agent import IsotopeAgent
    from isotope_agents.tui.app import run_tui

    config = IsotopeConfig.load()

    # CLI flags override config
    if preset:
        config.preset = preset
    if model:
        config.model = model
    if base_url:
        config.provider.base_url = base_url

    agent = IsotopeAgent(
        preset=config.preset,
        config=config,
        session_id=session_id,
    )

    try:
        asyncio.run(run_tui(agent))
    except KeyboardInterrupt:
        print("\nBye!")
        sys.exit(0)


@main.command()
@click.argument("prompt")
@click.option(
    "--preset",
    default=None,
    type=click.Choice(list(PRESETS.keys())),
    help="Preset to use",
)
@click.option("--model", default=None, help="Model to use")
@click.option("--base-url", default=None, help="Provider base URL")
@click.option(
    "--print", "print_mode", is_flag=True, help="Non-interactive output (print only)"
)
def run(
    prompt: str,
    preset: str | None,
    model: str | None,
    base_url: str | None,
    print_mode: bool,
) -> None:
    """Run a one-shot prompt."""
    from isotope_agents.agent import IsotopeAgent
    from isotope_agents.tui.output import tui_print

    config = IsotopeConfig.load()

    if preset:
        config.preset = preset
    if model:
        config.model = model
    if base_url:
        config.provider.base_url = base_url

    agent = IsotopeAgent(preset=config.preset, config=config)

    async def _run() -> None:
        collected_text = ""
        async for event in agent.agent.prompt(prompt):
            if event.type == "message_update":
                delta = getattr(event, "delta", None)
                if delta:
                    if print_mode:
                        collected_text += delta
                    else:
                        print(delta, end="", flush=True)

            elif event.type == "tool_start":
                if not print_mode:
                    tool_name = getattr(event, "tool_name", "?")
                    tui_print(f"\n  [calling {tool_name}]", style="tool")

            elif event.type == "tool_end":
                is_error = getattr(event, "is_error", False)
                if not print_mode and is_error:
                    tui_print("  [tool error]", style="err")

        if print_mode:
            print(collected_text)
        else:
            print()  # Final newline

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        sys.exit(130)


@main.command()
@click.option("--delete", "delete_id", default=None, help="Delete a session by ID")
def sessions(delete_id: str | None) -> None:
    """List or manage saved sessions."""
    from isotope_agents.session import SessionStore

    store = SessionStore()

    if delete_id:
        if store.delete(delete_id):
            click.echo(f"Deleted session: {delete_id}")
        else:
            click.echo(f"Session not found: {delete_id}", err=True)
            sys.exit(1)
        return

    listing = store.list()
    if not listing:
        click.echo("No saved sessions.")
        return

    # Print a formatted table — use rich if available
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Saved Sessions")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Updated", style="green")
        table.add_column("Msgs", justify="right", style="magenta")
        table.add_column("Summary")

        for meta in listing:
            updated = datetime.fromtimestamp(meta.updated_at, tz=UTC).strftime(
                "%Y-%m-%d %H:%M"
            )
            table.add_row(meta.id[:36], updated, str(meta.message_count), meta.summary)

        Console().print(table)
    except ImportError:
        # Fallback to plain text
        click.echo(f"{'ID':<40} {'Updated':<20} {'Msgs':>5}  {'Summary'}")
        click.echo("─" * 90)
        for meta in listing:
            updated = datetime.fromtimestamp(meta.updated_at, tz=UTC).strftime(
                "%Y-%m-%d %H:%M"
            )
            short_id = meta.id[:36]
            click.echo(f"{short_id:<40} {updated:<20} {meta.message_count:>5}  {meta.summary}")


if __name__ == "__main__":
    main()
