# Pixfabrica on Pinokio

1-click install and launch for the [Pixfabrica](https://github.com/AlexNolasco/pixfabrica) motion graphics editor (Vite + API on the host).

## Install in Pinokio

```bash
pterm download https://github.com/AlexNolasco/pixfabrica.git pixfabrica.pinokio.git
```

Then open the app in Pinokio and run **Install**, then **Start**.

## What Start does

- Runs `pnpm dev:all` (editor + API), same stack as local `run-all`
- Editor: http://localhost:5173
- API docs: http://localhost:8000/docs
- Uses host OpenGL when available (best path for GPU Play on Windows/macOS)

## Optional: Ollama

The compose agent needs [Ollama](https://ollama.com/) on the machine.
Install is not blocked without it.

## Update / Reset

- **Update** - `git pull`, then `uv sync --all-packages` and `pnpm install`
- **Reset** - removes `.venv` and `web/node_modules` only (does not wipe media or jobs)

## Requirements

| Tool | Role |
|------|------|
| uv + Python 3.12 | API, renderer, plugins |
| Node.js + pnpm | Web editor |
| FFmpeg | Recommended for MP4 export |
| Ollama | Optional compose agent |

Install bootstraps missing tools via Pinokio (`which` / conda / npm) when possible.

## GPU note

Realtime GPU preview needs a host OpenGL context.
Docker Desktop often falls back to software GL.
Prefer this Pinokio host launch for GPU Play.
