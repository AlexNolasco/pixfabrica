# pixfabrica-api

FastAPI server — job queue, plugin discovery, render triggering, and the starter gallery.

## Quick start

```bash
# From the repo root
uv sync --all-packages

# Optional: full local render limits (vertical presets, 4K, 60fps)
cp api/.env.example api/.env

# Manual API (bash) — source api/.env first if you copied it
set -a && source api/.env && set +a
uv run uvicorn pixfabrica_api.main:app --reload --port 8000
```

`pnpm dev:all` and `run-all.sh` load `api/.env` automatically when present.

Without `api/.env`, the API uses **hosted defaults** (600s, 1920×1080, 30fps). Vertical platform presets need a higher `PIXFABRICA_MAX_HEIGHT` — see `api/.env.example`.

API docs are available at `http://localhost:8000/docs` once the server is running.

## Endpoints

Route groups include `jobs`, `plugins`, `preview`, `gallery`, `media`, `pexels`, `compose`, and others. See `/docs` for the full reference.

`POST /compose/chat` is the compose-agent entry point. It returns **503** when `GET /health` reports `compose.ready: false` and **502** when Ollama chat fails. When ready, it runs an Ollama tool loop (`list_catalog_clips`, `build_graph`, `list_theme_presets`, `apply_job_theme`, `validate_graph`, …) and returns a validated `project` when possible.

`GET /health` returns FFmpeg availability, Ollama daemon status, compose-model readiness, Pexels stock-photo availability, and server version.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:<PIXFABRICA_WEB_PORT>` (default web port 5173), plus 5173 and 4173 | Comma-separated CORS origins |
| `PIXFABRICA_MEDIA_ROOT` | `media/` (cwd-relative) | Uploaded and bundled user media |
| `PIXFABRICA_GALLERY_ROOT` | `api/media/gallery/` | Starter composition gallery |
| `PUBLIC_API_URL` | request base URL | Canonical API base for upload/gallery thumbnail URLs |
| `PIXFABRICA_OLLAMA_BASE_URL` | — | Ollama HTTP base URL (overrides `OLLAMA_HOST`) |
| `OLLAMA_HOST` | `127.0.0.1:11434` | Ollama's own host setting; used when Pixfabrica override unset |
| `PIXFABRICA_COMPOSE_MODEL` | `qwen2.5:14b` | Compose chat model; must be installed with `tools` capability |
| `PIXFABRICA_COMPOSE_NUM_CTX` | `32768` | Ollama `num_ctx` for compose chat requests |
| `PIXFABRICA_COMPOSE_NUM_PREDICT` | `4096` | Max generated tokens per Ollama round-trip |
| `PIXFABRICA_COMPOSE_KEEP_ALIVE` | `30m` | Keep the compose model loaded between tool rounds |
| `PIXFABRICA_COMPOSE_MAX_TURNS` | `10` | Max Ollama round-trips (tool loops) per user message |
| `PIXFABRICA_COMPOSE_TIMEOUT` | `120` | Ollama chat HTTP timeout in seconds (raise for large models, e.g. `300`) |
| `PIXFABRICA_MAX_DURATION_S` | `600` | Max render duration (seconds) |
| `PIXFABRICA_MAX_WIDTH` | `1920` | Max output width (pixels) |
| `PIXFABRICA_MAX_HEIGHT` | `1080` | Max output height (pixels) |
| `PIXFABRICA_MAX_FPS` | `30` | Max output frame rate |
| `PIXFABRICA_MAX_PREVIEW_LONG_SIDE` | `480` | Max preview long side (pixels); default from `core/preview_dims.py` |
| `PIXFABRICA_MAX_TRACKS` | `16` | Max tracks per project |
| `PIXFABRICA_MAX_CLIPS_PER_TRACK` | `8` | Max clips per track |
| `PIXFABRICA_DEFAULT_LOCALE` | `en` | Deployment default BCP-47 locale (`en`, `es`, `zh-CN`, `ja`); exposed in `GET /config` |
| `PIXFABRICA_PEXELS_API_KEY` | — | [Pexels API](https://www.pexels.com/api/) key for **View → Stock Photos…** (server-side only; never sent to the browser) |
| `PIXFABRICA_PEXELS_DEFAULT_QUERIES` | `inspirational,music` | Comma-separated quick-pick search tags (first tag loads on open); exposed in `GET /config` when Pexels is configured |
| `PIXFABRICA_PEXELS_DEFAULT_VIDEO_QUERIES` | `cinematic,abstract,motion` | Quick-pick tags for **View → Stock Videos…**; exposed as `pexels_default_video_queries` in `GET /config` |
Copy `api/.env.example` → `api/.env` for local-dev values that match `docker/compose.yml` (3600s, 3840×2160, 60fps).

`POST /compose/chat` accepts optional `job_context` (`colors`, `palette_source`) — a snapshot of the editor theme on each message. Theme tools: `list_theme_presets`, `apply_job_theme` (named preset, `use_editor_theme`, or token overrides).


**Compose latency:** each tool step is a sequential Ollama inference pass. A typical turn costs 3–6 passes (`list_catalog_clips` → `build_graph` → `validate_graph` → reply). The GPU speeds each pass, but total wall time is roughly `passes × per-pass latency`. Responses include `timing.ollama_calls` and `timing.elapsed_ms` for diagnosis.

For faster compose on a local GPU:

- Use a smaller tool-capable model (`qwen2.5:14b`, `qwen3:8b`) instead of 30B+ models
- Lower `PIXFABRICA_COMPOSE_NUM_CTX` to `8192` or `16384` unless you need long chat history
- Keep the model warm (`ollama run <model>` in another terminal, or rely on `PIXFABRICA_COMPOSE_KEEP_ALIVE`)

## Stock photos (Pexels)

When `PIXFABRICA_PEXELS_API_KEY` is set, the web UI shows **View → Stock Photos…** and **View → Stock Videos…**. The API proxies search to Pexels and ingests selected media into `PIXFABRICA_MEDIA_ROOT`. The key stays on the server; the client only reads `pexels_available` from `GET /health` and quick-pick tags from `GET /config` (`pexels_default_queries`, `pexels_default_video_queries`).

| Method | Path | Description |
|---|---|---|
| `GET` | `/pexels/search` | Search photos (`query`, `orientation`, `page`, `per_page`) |
| `POST` | `/pexels/apply` | Download + optimize a photo for `std-background-image` |
| `GET` | `/pexels/videos/search` | Search videos (`query`, `orientation`, `page`, `per_page`) |
| `POST` | `/pexels/videos/apply` | Download + optimize a video for `std-video` |
| `GET` | `/pexels/orientation` | Map project width/height → `portrait` / `landscape` / `square` |

Without the env var, Pexels routes return **503** and the menu item is hidden.

## Starter gallery

The web UI **File → Start from Gallery…** loads curated starters from `PIXFABRICA_GALLERY_ROOT` (default `api/media/gallery/`).

### Folder layout (bundle-first)

Each starter is a **portable project bundle** plus picker thumbnail. Optional metadata JSON keeps list text without opening the zip.

```
{PIXFABRICA_GALLERY_ROOT}/
  {category}/
    {slug}.pixfabrica.zip   # project.json + assets/ (required for bundle starters)
    {slug}.webp             # picker thumbnail (.webp, .jpg, .jpeg, or .png)
    {slug}.json             # optional metadata: { "title", "description" }
```

- **category** and **slug** must match `[A-Za-z0-9_-]+`.
- A starter appears when it has a **thumbnail** and either a **bundle** or a **legacy full project JSON**.
- **title** / **description** come from `{slug}.json` when present, otherwise from `project.json` inside the bundle.

**Load path:** bundle starters are imported into `media/bundles/gallery/{category}/{slug}/` on first open (assets stay inside the bundle). Legacy JSON starters still use portable `media/…` refs under `PIXFABRICA_MEDIA_ROOT`.

### HTTP routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/gallery` | List categories and starter metadata |
| `GET` | `/gallery/{category}/{slug}` | Load starter project JSON (with media refs resolved) |
| `GET` | `/gallery/thumbnails/{category}/{slug}` | Thumbnail image (public, no auth) |
| `POST` | `/gallery/publish` | Publish starter from web project JSON + thumbnail (dev; see below) |

### Legacy JSON starters

Older starters may still use a full project `{slug}.json` with portable refs:

```json
"source": "media/snippet.mp3"
```

On load, `media/…` strings are rewritten to absolute paths under `PIXFABRICA_MEDIA_ROOT`. Prefer bundles for repo/Docker curation.

### Authoring a curated starter

1. Build in the editor → **Export project bundle** (`.pixfabrica.zip`).
2. Capture a picker frame as `{slug}.webp` (or `.png`).
3. Place under `{category}/`:
   - `{slug}.pixfabrica.zip`
   - `{slug}.webp`
   - optional `{slug}.json` with `title` and `description` only
4. Commit `api/media/gallery/**` (tracked in git; not the dev `media/` upload folder).

### Publishing from the web (development)

When running the Vite dev server (`import.meta.env.DEV`), **File → Add to Gallery…** posts to `POST /gallery/publish`. The API writes `{slug}.pixfabrica.zip`, metadata `{slug}.json`, and the thumbnail — it does **not** copy assets into the global `media/` folder.

Disable in production with `PIXFABRICA_GALLERY_PUBLISH=0` (enabled by default).

### Tests

Gallery behaviour is covered in `api/tests/test_gallery_routes.py`, `test_gallery_media.py`, and `test_gallery_publish.py`.
