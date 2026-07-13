import asyncio
import os
import shutil
from contextlib import asynccontextmanager, suppress
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pixfabrica_api.auth import auth_middleware
from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.demo_audio import warmup_demo_audio
from pixfabrica_api.gl_policy import gl_capability_payload
from pixfabrica_api.job_service import job_service
from pixfabrica_api.ollama_settings import ollama_health
from pixfabrica_api.pexels_settings import pexels_available
from pixfabrica_api.routes import (
    audio_analyze,
    catalog,
    compose,
    config,
    fonts,
    gallery,
    jobs,
    media,
    pexels,
    plugins,
    preview,
    preview_clip,
    project_bundles,
    theme,
)
from pixfabrica_core.fonts import FontManifestError, rebuild_font_catalog


@asynccontextmanager
async def lifespan(_app: FastAPI):
    rebuild_catalog_cache()
    with suppress(FontManifestError):
        rebuild_font_catalog()  # GET /fonts returns 503 until assets/fonts is populated
    with suppress(Exception):
        await warmup_demo_audio(30.0)
    job_service.start(asyncio.get_running_loop())
    yield


app = FastAPI(title="Pixfabrica API", version="0.1.0", lifespan=lifespan)

_dev_web_port = os.environ.get("PIXFABRICA_WEB_PORT", "5173").strip() or "5173"
_dev_origins = [
    f"http://localhost:{_dev_web_port}",
    "http://localhost:5173",
    "http://localhost:4173",
]
_env_origins = os.environ.get("ALLOWED_ORIGINS", "")
_origins = [o.strip() for o in _env_origins.split(",") if o.strip()] or _dev_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(auth_middleware)

app.include_router(config.router)
app.include_router(compose.router)
app.include_router(fonts.router)
app.include_router(theme.router)
app.include_router(media.router)
app.include_router(pexels.router)
app.include_router(audio_analyze.router)
app.include_router(plugins.router)
app.include_router(catalog.router)
app.include_router(gallery.router)
app.include_router(preview.router)
app.include_router(preview_clip.router)
app.include_router(project_bundles.router)
app.include_router(jobs.router)


class ComposeHealthResponse(BaseModel):
    model: str
    model_available: bool
    tools_capable: bool | None
    ready: bool
    reason: str | None = None


class GlHealthResponse(BaseModel):
    available: bool
    reason: str | None = None
    renderer: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ffmpeg: bool
    gl: GlHealthResponse
    ollama: bool
    compose: ComposeHealthResponse
    pexels_available: bool
    version: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ollama = ollama_health()
    compose = ollama.compose
    gl_payload = gl_capability_payload()
    return HealthResponse(
        status="ok" if ffmpeg_ok else "degraded",
        ffmpeg=ffmpeg_ok,
        gl=GlHealthResponse(
            available=bool(gl_payload.get("gl_available")),
            reason=gl_payload.get("gl_reason"),
            renderer=gl_payload.get("gl_renderer"),
        ),
        ollama=ollama.available,
        compose=ComposeHealthResponse(
            model=compose.model,
            model_available=compose.model_available,
            tools_capable=compose.tools_capable,
            ready=compose.ready,
            reason=compose.reason,
        ),
        pexels_available=pexels_available(),
        version=app.version,
    )
