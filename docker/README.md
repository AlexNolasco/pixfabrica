# Pixfabrica Docker demo

Run the editor and API in containers — one browser URL, persistent data on the host.

## Who this is for

| Use case | Use Docker? |
|----------|-------------|
| Linux boxed demo / VPS (skip installing uv, pnpm, FFmpeg) | Yes |
| Linux + NVIDIA, want GL tracks in compose | Yes — add `compose.gpu.yml` |
| Windows or macOS, realtime Play + OpenGL | **No** — use repo-root `run-all` instead |
| Windows Docker Desktop “with GPU” | Expect CPU / `llvmpipe`; do not rely on it for GL |

Native `run-all` is the supported path for local GPU preview on Windows and macOS.
Docker here is optional packaging, especially for Linux hosts.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| [Docker](https://docs.docker.com/get-docker/) + Compose v2 | `docker compose version` |
| **GPU (optional, Linux)** | **NVIDIA:** [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). **AMD:** Linux + `amdgpu` + Mesa — see [GPU passthrough](#gpu-passthrough) |
| FFmpeg | Included in the API image |

Without GPU passthrough, the stack still starts; `GET /health` reports `gl.available: false` and GL-heavy projects are blocked (same as local `doctor` without OpenGL).

## Quick start

From the **repo root**:

```bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/compose.yml up --build
```

Open **http://localhost:8080** (override with `HOST_PORT` in `docker/.env`).

Stop: `Ctrl+C`, then optionally `docker compose --env-file docker/.env -f docker/compose.yml down`.

## GPU passthrough

The API image uses **headless EGL** (not X11/GLX) for ModernGL. Pick **one** overlay — do not combine NVIDIA and AMD files.

Build arg `GL_VENDOR` in `docker/Dockerfile.api`:

| Value | When | Image adds |
|-------|------|------------|
| `none` (default) | CPU demo, no GPU overlay | Base EGL/GLVND only — `gl.available` stays false |
| `nvidia` | `compose.gpu.yml` | NVIDIA EGL ICD (driver libs injected by Container Toolkit) |
| `mesa` | `compose.gpu.amd.yml` | Mesa DRI (`radeonsi`) for AMD `/dev/dri` passthrough |

Check **http://localhost:8080/api/health** for `gl.available`, `gl.renderer`, and `ffmpeg`.

### NVIDIA (Linux)

Requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) on a Linux host.

```bash
docker compose --env-file docker/.env \
  -f docker/compose.yml -f docker/compose.gpu.yml up --build
```

If `gl.available` is false with `XOpenDisplay`, rebuild the API image and use this overlay (not the base compose file alone).

On Windows/macOS Docker Desktop, this overlay usually still reports software GL.
Use `run-all` on the host for OpenGL instead.
### AMD (Linux host)

Requires a working **amdgpu** kernel driver and Mesa on the host. There is no AMD equivalent of NVIDIA Container Toolkit — pass **`/dev/dri`** into the container instead.

1. Add your host `render` group GID to `docker/.env`:

   ```bash
   echo "GPU_RENDER_GID=$(getent group render | cut -d: -f3)" >> docker/.env
   ```

   If `render` does not exist, try `video`: `getent group video | cut -d: -f3`.

2. Start with the AMD overlay:

   ```bash
   docker compose --env-file docker/.env \
     -f docker/compose.yml -f docker/compose.gpu.amd.yml up --build
   ```

3. Confirm `/api/health` reports `gl.available: true` and a Radeon renderer (not `llvmpipe`).

**Notes:** AMD GPU in Docker is less turnkey than NVIDIA. If EGL fails, Mesa versions between host and container may need alignment, or you may need `MESA_LOADER_DRIVER_OVERRIDE=radeonsi` in the AMD overlay env. Windows/macOS Docker with AMD GPUs is not supported for container GL — run the API natively on the host instead.

## Architecture

Two images, one public port:

```
Browser → web (nginx :8080) → api (uvicorn :8000, internal)
              ├─ /              static React SPA
              ├─ /api/*         proxied to API
              └─ /ws/*          WebSocket proxy (preview, jobs)
```

Build from the repo (no prebuilt registry images in v1):

| Image | Dockerfile | Contents |
|-------|------------|----------|
| `web` | `docker/Dockerfile.web` | nginx + `pnpm build` output |
| `api` | `docker/Dockerfile.api` | Python 3.12 (slim), FastAPI, renderer, plugins, bundled fonts. `GL_VENDOR` build arg: `none` / `nvidia` / `mesa` (~2 GB image; multi-stage, no CLI) |

## Configuration (`docker/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `API_TOKEN` | `pixfabrica-dev-token` | Shared bearer token (local demo only). Baked into the web image at **build** time — changing it requires `docker compose … build web`. |
| `PIXFABRICA_DATA_DIR` | `./pixfabrica-data` | Host folder bind-mounted to `/data` in the API container |
| `HOST_PORT` | `8080` | Published nginx port |
| `PIXFABRICA_OLLAMA_BASE_URL` | *(unset)* | Set to `http://ollama:11434` when using the compose profile (below) |
| `PIXFABRICA_DEFAULT_LOCALE` | `en` | Deployment default locale on first visit (`en`, `es`, `zh-CN`, `ja`); also API `lang` fallback |

### Data layout (inside the API container)

All paths are fixed in `compose.yml`; only the host bind is configurable:

| Path | Env var |
|------|---------|
| `/data/media` | `PIXFABRICA_MEDIA_ROOT` |
| `/data/jobs` | `PIXFABRICA_JOBS_ROOT` |
| `/data/cache` | `PIXFABRICA_CACHE_DIR` |
| `/data/user-fonts` | `PIXFABRICA_USER_FONTS_DIR` |
| `/data/temp` | `PIXFABRICA_TEMP_DIR` |

Bundled fonts and the starter gallery ship **inside the API image** (`assets/fonts`, `api/media/gallery` with `.pixfabrica.zip` starters).

Gallery publishing from the UI is disabled (`PIXFABRICA_GALLERY_PUBLISH=0`).

## Compose agent (optional)

Ollama is **off by default**. To enable the compose chat agent:

1. Uncomment in `docker/.env`:

   ```env
   PIXFABRICA_OLLAMA_BASE_URL=http://ollama:11434
   ```

2. Start with the `compose` profile:

   ```bash
   docker compose --env-file docker/.env \
     -f docker/compose.yml --profile compose up --build
   ```

3. Pull a tool-capable model inside the Ollama container (example):

   ```bash
   docker compose --env-file docker/.env -f docker/compose.yml exec ollama \
     ollama pull qwen2.5:14b
   ```

Verify with `/api/health` → `compose.ready: true`.

## API token in the browser

The web app sends `Authorization: Bearer <token>`. For local demo the default token matches `api/README.md`. Do not expose port `8080` to the internet without changing `API_TOKEN` and rebuilding the web image.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| 401 on API calls | `API_TOKEN` mismatch — rebuild web after changing `.env` |
| GL tracks disabled | NVIDIA: add `compose.gpu.yml` and confirm Container Toolkit. AMD: add `compose.gpu.amd.yml`, set `GPU_RENDER_GID`, confirm `/dev/dri` on host |
| Renders fail | `/api/health` → `ffmpeg: false` (should not happen in the API image) |
| Compose agent 503 | Ollama profile not running, model not pulled, or `PIXFABRICA_OLLAMA_BASE_URL` unset |

## Related

- Local dev (hot reload): [README](../README.md) → `run-all.sh`
- API env reference: [api/README.md](../api/README.md)
