# Agent onboarding

Operational guide for AI coding assistants working in this repo. For design rationale and deep context, follow the links — do not treat this file as a substitute for [Architecture](docs/ARCHITECTURE.md).

## General Guidelines

Hard rules. When in doubt, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the why.
- Never use the em dash "-". Use plain dash "-" instead
- When writing commit messages, NEVER auto-add your agent name as co-author
- Never manually modify CHANGELOG.md files or any files that are marked as auto-generated
- When writing or substantially editing long Markdown files, put each full sentence on its own line.
  Preserve normal Markdown structure, but avoid wrapping multiple sentences onto one physical line.
- When making technical decisions, do not give much weight to development cost.
  Instead, prefer quality, simplicity, robustness, scalability, and long term maintainability.
- When doing bug fixes, always start with reproducing the bug in an E2E setting as closely aligned with how an end use
  This makes sure you find the real problem so your fix will actually solve it.
- When end-to-end testing a product, be picky about the UI you see and be obsessed with pixel perfection.
  If something clearly looks off, even if it is not directly related to what you are doing, try to get it fixed along 
- Apply that same high standard to engineering excellence: lint, test failures, and test flakiness.   If you see one, 
  even if it is not caused by what you are working on right now, still get it fixed.
- **Python 3.12 only** — `requires-python = ">=3.12,<3.13"` across workspace packages.
- **Use `uv`** for Python deps and commands from the repo root (`uv sync`, `uv run pytest`, `uv run pixfabrica …`).
- **Use `pnpm` in `web/`** — never npm or yarn.
- **Do not re-add React Flow** — the timeline editor replaced the node graph UI; `@xyflow/react` must stay removed.
- **Timeline is king** — the web UI is timeline-based, not a node graph editor. Bias toward presets and opinionated defaults over fine-grained controls.
- **Kidbashing model** — plugins are pre-built animated pieces users stack and lightly tune; defaults must work out of the box.
- **Prefer WGSL/GPU plugins** for visual flair; Skia is mainly for text and 2D paths.
- **Do not hardcode user-facing web strings** — use `web/src/lib/i18n.messages.json` and `useT` / `TranslationKey`.
- **Plugin param labels** come from `schema.nls.json` (via `pixfabrica plugin gen-nls`), not the frontend.
- **base-ui gotcha** — `DropdownMenuTrigger` does not support `asChild`; style the trigger directly.
- **Run tests before finishing Python work** — `uv run pytest -m "not ffmpeg"` from repo root.
- **Run `pnpm build` after significant web/TS changes** — catches errors the dev server may miss.
- **Keep changes focused** — one logical change per PR when possible ([CONTRIBUTING.md](CONTRIBUTING.md)).

## Setup & commands

Prerequisites and ports: [README.md](README.md). Contribution workflow: [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
# First-time setup (or after pulling dependency changes)
./doctor.sh && ./setup.sh          # macOS / Linux
doctor.bat && setup.bat            # Windows

# Equivalent manual setup
uv sync --all-packages
cd web && pnpm install

# Dev — editor + API (defaults: Vite :5173, API :8000)
./run-all.sh                       # or: cd web && pnpm dev:all

# Python tests (skip slow FFmpeg integration tests)
uv run pytest -m "not ffmpeg"

# Python lint
uv run ruff check .

# Web typecheck + production build
cd web && pnpm build

# CLI help
uv run --package pixfabrica-cli pixfabrica --help
```

| Service | Default URL |
|---------|-------------|
| Editor | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| API health | http://localhost:8000/health |

Local API token: `pixfabrica-dev-token` (see [api/README.md](api/README.md)).

## Where to work

| If you're changing… | Start here |
|---------------------|------------|
| Shared models / graph / audio / themes | [core/README.md](core/README.md) |
| HTTP API / jobs / preview / compose agent | [api/README.md](api/README.md) |
| Render engine / Skia / GPU compositor | [renderer/README.md](renderer/README.md) |
| CLI commands / scaffolding | [cli/README.md](cli/README.md) |
| Web UI / timeline / preview | [web/README.md](web/README.md) — see **Web** below |
| Plugins / clips / effects | [plugins/README.md](plugins/README.md) — see **Plugins** below |
| System design / UI philosophy / plugin contract | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Docker (Linux boxed demo; not Windows GPU Play) | [docker/README.md](docker/README.md) |

Workspace members (root [pyproject.toml](pyproject.toml)): `core`, `api`, `renderer`, `cli`, `plugins/std`, `plugins/std_effects`.

## Web

- **Dev:** `cd web && pnpm dev:all` (Vite + API concurrently).
- **Verify:** `cd web && pnpm build` after non-trivial TypeScript/React changes.
- **Stack:** React 19, TypeScript, Vite, Tailwind v4, Zustand + Zundo, shadcn/ui on **base-ui**, `@xzdarcy/react-timeline-editor`.
- **i18n:** edit English in `web/src/lib/i18n.messages.json`, then `uv run pixfabrica web gen-i18n web` for other locales (Ollama).
- **UI model & gotchas:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (Web UI section).

## Plugins

- **Scaffold:** `uv run pixfabrica plugin new <name> -o plugins` from repo root.
- **Built-in library:** `plugins/std/` (clips); lightweight GL/Skia effects in `plugins/std_effects/`.
- **Community plugins:** cloned under `plugins/` and registered with `uv add --editable ./plugins/<name> --no-workspace` (see [plugins/README.md](plugins/README.md)).
- **Labels / NLS:** after param or label changes, `uv run pixfabrica plugin gen-nls` (Ollama).
- **Tests:** root pytest covers most packages; std plugin tests live in `plugins/std/tests/` — run explicitly when touching std clips:

  ```bash
  uv run pytest plugins/std/tests/
  ```

- **Full authoring contract:** [plugins/README.md](plugins/README.md).

## Further reading

- [README.md](README.md) — quick start, repo map, ports
- [CONTRIBUTING.md](CONTRIBUTING.md) — PR expectations, dev commands
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — design, dataflow, constraints in depth
- [docs/ROADMAP.md](docs/ROADMAP.md) — planned follow-ups
