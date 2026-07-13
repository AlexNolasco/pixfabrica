"""Named palette catalog and image extraction endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.presets import ThemeName, ThemeVariant, list_theme_presets
from pixfabrica_std.config.basic_themes import palette_from_source

log = logging.getLogger("pixfabrica.api.theme")

router = APIRouter(prefix="/theme", tags=["theme"])


class ThemePresetResponse(BaseModel):
    theme: ThemeName
    variant: ThemeVariant
    label: str
    colors: dict[str, str]


class ExtractPaletteRequest(BaseModel):
    source: str = Field(description="HTTP(S) URL or absolute path to an image file")


@router.get("/presets", response_model=list[ThemePresetResponse])
async def list_presets() -> list[ThemePresetResponse]:
    rows = list_theme_presets()
    return [ThemePresetResponse.model_validate(row) for row in rows]


@router.post("/extract", response_model=dict[str, str])
async def extract_palette(body: ExtractPaletteRequest) -> dict[str, str]:
    source = body.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="source is required")
    try:
        palette: ColorPalette = await palette_from_source(source)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportError as exc:
        log.exception("palette extraction unavailable")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("palette extraction failed for %r", source)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return palette.model_dump(mode="json")
