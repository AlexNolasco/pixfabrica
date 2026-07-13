from __future__ import annotations

import asyncio
import locale as _locale_mod
import signal
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from pixfabrica_cli.commands import fonts as fonts_commands
from pixfabrica_cli.commands import plugin as plugin_commands
from pixfabrica_cli.commands import web as web_commands

if TYPE_CHECKING:
    from pixfabrica_core.clips import RenderJob

app = typer.Typer(name="pixfabrica", help="Pixfabrica — programmatic video generation.")
app.add_typer(fonts_commands.app, name="fonts")
app.add_typer(plugin_commands.app, name="plugin")
app.add_typer(web_commands.app, name="web")

_console = Console(stderr=True)


def _detect_locale() -> str:
    try:
        lang, _ = _locale_mod.getlocale()
        if lang:
            return lang.replace("_", "-").split(".")[0]
    except Exception:
        pass
    return "en"


@app.command()
def render(
    graph: Annotated[
        Path,
        typer.Argument(help="Path to graph JSON or .pixfabrica.zip bundle", exists=True),
    ],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output video path")] = Path(
        "output.mp4"
    ),
    width: Annotated[int | None, typer.Option("--width", help="Override output width")] = None,
    height: Annotated[int | None, typer.Option("--height", help="Override output height")] = None,
    fps: Annotated[float | None, typer.Option("--fps", help="Override output frame rate")] = None,
    locale: Annotated[
        str | None, typer.Option("--locale", help="Locale for error messages (e.g. en, es)")
    ] = None,
) -> None:
    """Render a graph JSON or portable bundle to video."""
    from pixfabrica_core.catalog import build_catalog_cache
    from pixfabrica_core.composition.effect_registry import register_effect
    from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
    from pixfabrica_core.errors import RenderError
    from pixfabrica_core.open_render_job import open_render_job
    from pixfabrica_core.plugins.discovery import discover_plugins

    active_locale = locale or _detect_locale()

    # ── Plugin discovery ────────────────────────────────────────────────────
    discovered, failed = discover_plugins()
    for f in failed:
        _console.print(
            f"[yellow]Warning:[/yellow] plugin '{f.package_name}' failed to load: {f.error}"
        )
    for plugin in discovered:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for cfg_cls in plugin.project_settings:
            register_setting_type(cfg_cls)
        for effect_cls in plugin.effects:
            register_effect(effect_cls)

    # ── Cancellation via Ctrl+C ─────────────────────────────────────────────
    cancel = threading.Event()

    def _on_sigint(sig: int, frame: object) -> None:
        cancel.set()

    signal.signal(signal.SIGINT, _on_sigint)

    # ── Load & validate JSON or bundle ─────────────────────────────────────
    catalog = build_catalog_cache(discovered)
    try:
        with open_render_job(graph, catalog=catalog) as job:
            from pixfabrica_core.job_effects import tracks_need_gl_context
            from pixfabrica_renderer.gl_probe import gl_available

            if not gl_available() and tracks_need_gl_context(job.tracks):
                _console.print(
                    "[red]Error:[/red] This project uses GL tracks or GPU effects, "
                    "but OpenGL is not available on this host."
                )
                raise typer.Exit(1)
            _run_render(job, output, width, height, fps, active_locale, cancel)
    except RenderError as exc:
        _console.print(f"[red]Error:[/red] {exc.format(active_locale)}")
        raise typer.Exit(1) from None

    _console.print(f"[green]✓[/green] {output}")


def _run_render(
    job: RenderJob,
    output: Path,
    width: int | None,
    height: int | None,
    fps: float | None,
    active_locale: str,
    cancel: threading.Event,
) -> None:
    from pixfabrica_core.errors import RenderError
    from pixfabrica_renderer.render import render_job

    async def _run() -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=_console,
            transient=False,
        ) as progress:
            task = progress.add_task("Preparing…", total=100)

            async for event in render_job(
                job, output, width=width, height=height, fps=fps, cancel=cancel
            ):
                if event.stage == "prepare":
                    progress.update(task, description="Preparing…", completed=0)
                elif event.stage == "render":
                    progress.update(
                        task,
                        description=f"Rendering frame {event.frame}/{event.total}",
                        completed=event.pct,
                    )
                elif event.stage == "done":
                    progress.update(task, description="Done", completed=100)
                elif event.stage == "cancelled":
                    progress.update(task, description="Cancelled")

    try:
        asyncio.run(_run())
    except RenderError as exc:
        _console.print(f"\n[red]Error:[/red] {exc.format(active_locale)}")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
