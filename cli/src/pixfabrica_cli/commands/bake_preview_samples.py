"""Bake all preview samples listed in preview-samples/sources.json."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from pixfabrica_cli.preview_bake import (
    bake_one_sample,
    loop_lengths_to_bake,
    sample_id_for_duration,
)
from pixfabrica_core.audio import AnalyzerKind
from pixfabrica_core.audio.preview_samples import (
    DEFAULT_BAKE_FPS,
    SHIPPED_ANALYZER,
    PreviewSamplesManifest,
    find_web_public,
    load_sources,
    manifest_path,
    resolve_source_path,
    save_manifest,
)

_console = Console(stderr=True)


def bake_preview_samples(
    web_public: Annotated[
        Path | None,
        typer.Option("--web-public", help="Path to web/public (auto-detected if omitted)"),
    ] = None,
    analyzer: Annotated[
        AnalyzerKind,
        typer.Option("--analyzer", "-a", help="Analyzer for all sources"),
    ] = SHIPPED_ANALYZER,
    fps: Annotated[float, typer.Option("--fps", help="Timeline frame rate")] = DEFAULT_BAKE_FPS,
    seek: Annotated[
        float, typer.Option("--seek", help="Start offset in each source (seconds)")
    ] = 0.0,
    beat_tightness: Annotated[
        float, typer.Option("--beat-tightness", help="Beat peak strictness")
    ] = 200.0,
    all_loops: Annotated[
        bool,
        typer.Option(
            "--all-loops",
            help="Bake 8, 15, and 45 seconds per source (ids like drums-8s)",
        ),
    ] = False,
    skip_audio: Annotated[
        bool,
        typer.Option("--skip-audio", help="Only write timeline.npz"),
    ] = False,
) -> None:
    """Bake every entry in preview-samples/sources.json (default 45s each) and rewrite manifest.json."""
    if fps <= 0:
        raise typer.BadParameter("--fps must be positive")

    public = (web_public or find_web_public()).resolve()
    sources = load_sources(public)
    if not sources:
        raise typer.BadParameter(
            f"No sources in {manifest_path(public).parent / 'sources.json'} — add Pixabay entries first."
        )

    lengths = loop_lengths_to_bake(seconds=None, all_loops=all_loops)
    multi = len(lengths) > 1
    baked: list = []
    errors: list[str] = []

    for src in sources:
        path = resolve_source_path(public, src)
        if not path.is_file():
            errors.append(f"missing source file: {path}")
            continue
        for duration in lengths:
            sid = sample_id_for_duration(src.id, duration, multiple_lengths=multi)
            _console.print(
                f"[cyan]Baking[/cyan] {src.label} ({sid}) — {duration}s, {analyzer.value}…"
            )
            try:
                entry = bake_one_sample(
                    web_public=public,
                    source_path=path,
                    sample_id=sid,
                    label=src.label if not multi else f"{src.label} ({int(duration)}s)",
                    seconds=duration,
                    fps=fps,
                    analyzer=analyzer,
                    seek=seek,
                    beat_tightness=beat_tightness,
                    source_url=src.source_url,
                    license_text=src.license,
                    skip_audio=skip_audio,
                )
                baked.append(entry)
                _console.print(f"  [green]✓[/green] {entry.timeline}")
            except Exception as exc:
                errors.append(f"{sid}: {exc}")
                _console.print(f"  [red]✗[/red] {sid}: {exc}")

    if not baked:
        raise typer.Exit(1)

    manifest = PreviewSamplesManifest(samples=baked)
    save_manifest(public, manifest)
    _console.print(f"[green]✓[/green] manifest: {len(baked)} samples → {manifest_path(public)}")

    if errors:
        for msg in errors:
            _console.print(f"[yellow]Warning:[/yellow] {msg}")
        raise typer.Exit(1)
