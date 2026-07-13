"""Typer group for web SPA maintenance commands."""

from __future__ import annotations

import typer

from pixfabrica_cli.commands.bake_preview_sample import bake_preview_sample
from pixfabrica_cli.commands.bake_preview_samples import bake_preview_samples
from pixfabrica_cli.commands.gen_typography import gen_typography
from pixfabrica_cli.commands.gen_web_i18n import gen_web_i18n

app = typer.Typer(help="Web SPA helpers.")
app.command("gen-i18n")(gen_web_i18n)
app.command("gen-typography")(gen_typography)
app.command("bake-preview-sample")(bake_preview_sample)
app.command("bake-preview-samples")(bake_preview_samples)
