"""Font manifest validation and woff2 build commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from pixfabrica_core.fonts import (
    build_font_catalog,
    default_bundled_fonts_dir,
    default_manifest_path,
    run_font_build,
)
from pixfabrica_core.fonts.manifest import FontManifestError

app = typer.Typer(help="Bundled font manifest and woff2 preview generation.")
_console = Console(stderr=True)


@app.command("build")
def fonts_build(
    fonts_dir: Annotated[
        Path | None,
        typer.Option("--fonts-dir", help="Bundled fonts directory (manifest + sources)"),
    ] = None,
    manifest: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to manifest.json"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate only; report missing or stale woff2"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Regenerate all woff2 files"),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Validate manifest sources and generate .woff2 siblings for web preview."""
    root = (fonts_dir or default_bundled_fonts_dir()).resolve()
    manifest_path = manifest or default_manifest_path(root)
    result = run_font_build(
        fonts_dir=root,
        manifest_path=manifest_path,
        dry_run=dry_run,
        force=force,
    )

    if verbose:
        for name in result.created:
            _console.print(f"[green]created[/green] {name}")
        for name in result.up_to_date:
            _console.print(f"[dim]up to date[/dim] {name}")
        for err in result.errors:
            _console.print(f"[red]error[/red] {err}")

    if not result.ok:
        for err in result.errors:
            _console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1)

    if dry_run:
        _console.print("[green]OK[/green] manifest and woff2 files are in sync")
    else:
        _console.print(
            f"[green]OK[/green] {len(result.created)} woff2 created, "
            f"{len(result.up_to_date)} up to date"
        )


@app.command("check")
def fonts_check(
    fonts_dir: Annotated[Path | None, typer.Option("--fonts-dir")] = None,
    manifest: Annotated[Path | None, typer.Option("--manifest")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """CI: fail if manifest is invalid or .woff2 previews are missing/stale.

    Does not require .ttf sources — only `fonts build` needs those to regenerate previews.
    """
    fonts_build(
        fonts_dir=fonts_dir,
        manifest=manifest,
        dry_run=True,
        force=False,
        verbose=verbose,
    )


@app.command("list")
def fonts_list(
    fonts_dir: Annotated[Path | None, typer.Option("--fonts-dir")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print raw catalog JSON")] = False,
) -> None:
    """Print the resolved font catalog (manifest + optional extra dir)."""
    root = (fonts_dir or default_bundled_fonts_dir()).resolve()
    try:
        catalog = build_font_catalog(bundled_dir=root)
    except FontManifestError as exc:
        _console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    if as_json:
        payload = [
            {
                "id": f.id,
                "family": f.family,
                "label": f.label,
                "category": f.category,
                "weights": [
                    {"value": w.value, "preview_url": w.preview_url, "source": w.source}
                    for w in f.weights
                ],
            }
            for f in catalog
        ]
        typer.echo(json.dumps(payload, indent=2))
        return

    for family in catalog:
        weights = ", ".join(str(w.value) for w in family.weights)
        _console.print(f"{family.id} ({family.category}) — {family.family} [{weights}]")
