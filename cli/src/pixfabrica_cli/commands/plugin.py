from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pixfabrica_cli.commands.gen_nls import gen_nls
from pixfabrica_cli.commands.gen_notices import gen_notices
from pixfabrica_cli.commands.gen_ui import gen_ui
from pixfabrica_cli.scaffold import scaffold_plugin
from pixfabrica_core.plugins.discovery import discover_plugins

console = Console()
app = typer.Typer(help="Manage Pixfabrica plugins.")
app.command("gen-nls")(gen_nls)
app.command("gen-notices")(gen_notices)
app.command("gen-ui")(gen_ui)


@app.command("new")
def new(
    name: Annotated[str, typer.Argument(help="Plugin slug, e.g. 'acme-rain'")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Parent directory")] = Path(
        "."
    ),
) -> None:
    """Scaffold a new plugin package."""
    try:
        plugin_dir = scaffold_plugin(name, output_dir.resolve())
    except FileExistsError:
        console.print(f"[red]Error:[/red] '{name}' already exists at {output_dir.resolve()}")
        raise typer.Exit(1) from None

    console.print(f"[green]Created[/green] plugin [bold]{name}[/bold] at {plugin_dir}")
    try:
        rel_plugin = plugin_dir.relative_to(Path.cwd())
    except ValueError:
        rel_plugin = plugin_dir
    console.print("  From the Pixfabrica repo root:")
    console.print(f"    uv add --editable ./{rel_plugin.as_posix()} --no-workspace")
    console.print("    uv run pixfabrica plugin list --clip-types")
    console.print(f"  Plugin-only dev: cd {plugin_dir} && uv sync")


@app.command("list")
def list_plugins(
    clip_types: Annotated[
        bool,
        typer.Option("--clip-types", help="Show clip types exposed by each plugin."),
    ] = False,
) -> None:
    """List all installed Pixfabrica plugins."""
    show_clip_types = clip_types
    discovered, failed = discover_plugins()

    if not discovered and not failed:
        console.print("[dim]No plugins installed.[/dim]")
        console.print("  Clone a plugin into the plugins/ directory to install it.")
        return

    if discovered:
        table = Table(title="Installed Plugins", show_lines=False)
        table.add_column("Name", style="bold")
        table.add_column("Package")
        table.add_column("Version")
        table.add_column("Author", style="dim")
        if show_clip_types:
            table.add_column("Clip types")

        for p in discovered:
            manifest = p.manifest
            display = manifest.display_name if manifest else p.package_name
            row = [display, p.package_name, p.version, p.author or "—"]
            if show_clip_types:
                type_list = ", ".join(
                    n.clip_type for n in p.clip_types if getattr(n, "clip_type", "")
                )
                row.append(type_list or "—")
            table.add_row(*row)

        console.print(table)

    for f in failed:
        console.print(f"[red]Failed to load[/red] [bold]{f.package_name}[/bold]: {f.error}")
