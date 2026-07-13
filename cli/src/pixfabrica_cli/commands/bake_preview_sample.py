"""Bake a single preview audio sample into web/public."""

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
    DEFAULT_BAKE_SECONDS,
    SHIPPED_ANALYZER,
    find_web_public,
    load_manifest,
    manifest_path,
    save_manifest,
    slugify_sample_id,
)

_console = Console(stderr=True)


def bake_preview_sample(
    audio: Annotated[Path, typer.Argument(help="Source audio file", exists=True, dir_okay=False)],
    analyzer: Annotated[
        AnalyzerKind,
        typer.Option("--analyzer", "-a", help="Analyzer implementation"),
    ] = SHIPPED_ANALYZER,
    seconds: Annotated[
        float | None,
        typer.Option(
            "--seconds",
            "-s",
            help=f"Clip length (default {int(DEFAULT_BAKE_SECONDS)}s; ignored with --all-loops)",
        ),
    ] = None,
    fps: Annotated[float, typer.Option("--fps", help="Timeline frame rate")] = DEFAULT_BAKE_FPS,
    seek: Annotated[float, typer.Option("--seek", help="Start offset in source (seconds)")] = 0.0,
    beat_tightness: Annotated[
        float, typer.Option("--beat-tightness", help="Beat peak strictness (analyzer-dependent)")
    ] = 200.0,
    sample_id: Annotated[
        str | None,
        typer.Option("--id", help="Sample id (default: slug from filename)"),
    ] = None,
    label: Annotated[str | None, typer.Option("--label", help="Display label in web UI")] = None,
    web_public: Annotated[
        Path | None,
        typer.Option("--web-public", help="Path to web/public (auto-detected if omitted)"),
    ] = None,
    all_loops: Annotated[
        bool,
        typer.Option("--all-loops", help="Bake 8, 15, and 45 second variants"),
    ] = False,
    skip_audio: Annotated[
        bool,
        typer.Option("--skip-audio", help="Only write timeline.npz (no ffmpeg trim)"),
    ] = False,
) -> None:
    """Analyze one audio file and write preview bus timeline(s) under web/public/preview-samples/."""
    if fps <= 0:
        raise typer.BadParameter("--fps must be positive")

    public = (web_public or find_web_public()).resolve()
    base_id = slugify_sample_id(sample_id or audio.stem)
    display = label or audio.stem
    lengths = loop_lengths_to_bake(seconds=seconds, all_loops=all_loops)
    multi = len(lengths) > 1

    manifest = load_manifest(public)
    new_entries = []

    for duration in lengths:
        if duration <= 0:
            raise typer.BadParameter("--seconds must be positive")
        sid = sample_id_for_duration(base_id, duration, multiple_lengths=multi)
        entry_label = display if not multi else f"{display} ({int(duration)}s)"
        _console.print(
            f"[cyan]Analyzing[/cyan] {audio.name} → {sid} — {analyzer.value}, {duration}s @ {fps} fps…"
        )
        entry = bake_one_sample(
            web_public=public,
            source_path=audio,
            sample_id=sid,
            label=entry_label,
            seconds=duration,
            fps=fps,
            analyzer=analyzer,
            seek=seek,
            beat_tightness=beat_tightness,
            skip_audio=skip_audio,
        )
        new_entries.append(entry)
        _console.print(f"  timeline: {entry.timeline}")
        if not skip_audio:
            _console.print(f"  audio: {entry.audio}")

    ids = {e.id for e in new_entries}
    manifest.samples = [s for s in manifest.samples if s.id not in ids] + new_entries
    save_manifest(public, manifest)
    _console.print(f"[green]✓[/green] manifest updated ({manifest_path(public)})")
