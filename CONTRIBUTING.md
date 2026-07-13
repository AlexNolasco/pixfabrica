# Contributing

Thanks for exploring Pixfabrica. This project is early-stage; issues and PRs are welcome.

## Before you start

1. Read the [README](README.md) quick start.
2. Run `./doctor.sh` (or `doctor.bat`) — fix anything marked ✗.
3. Run `./setup.sh` (or `setup.bat`) — installs Python and web dependencies.

## Development commands

From the repo root:

```bash
# Web + API (same as run-all)
cd web && pnpm dev:all

# Python tests
uv run pytest -m "not ffmpeg"

# Lint / typecheck (optional locally; CI runs ruff + pytest + pnpm build on push/PR)
uv run ruff check .
cd web && pnpm build
```

Package-specific docs: `api/README.md`, `web/README.md`, `renderer/README.md`, `cli/README.md`.

## Pull requests

- Keep changes focused — one logical change per PR when possible.
- Run `pnpm build` if you touched `web/`.
- Run `uv run pytest -m "not ffmpeg"` if you touched Python packages.
- Follow existing code style (ruff for Python, eslint for web).

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the timeline model, legacy DAG graph, audio buses, and plugin system.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
