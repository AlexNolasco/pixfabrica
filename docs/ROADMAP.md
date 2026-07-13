# Roadmap

Post–initial-push follow-ups for the public GitHub release.

## Post–initial-push

- [ ] **GitHub Actions CI** — `uv sync`, `pytest -m "not ffmpeg"`, `pnpm install` + `pnpm build` on Ubuntu (Python 3.12)
- [ ] **CODE_OF_CONDUCT.md** — Contributor Covenant
- [ ] **Single-port hobbyist mode** — optional: serve prebuilt `web/dist` from the API (no Vite dev server at runtime)

## Ideas (unscheduled)

- Release tarballs with prebuilt web assets (runtime: Python + FFmpeg only)
- Docker image for local demo
- Expand `doctor` to optionally bootstrap `uv` via the official Astral installer
