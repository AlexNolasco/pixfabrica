# pixfabrica-web

React SPA for designing Pixfabrica render jobs — timeline-based.

See the root [README](../README.md) and [Architecture](../docs/ARCHITECTURE.md) for project-wide docs.

## Quick start

```bash
cd web
pnpm install
pnpm dev:all   # starts Vite + API server concurrently
```

## Stack

| | |
|---|---|
| Framework | React 19 + TypeScript + Vite |
| Styling | Tailwind CSS v4 |
| State | Zustand + Zundo (undo/redo) |
| Timeline | @xzdarcy/react-timeline-editor |
| UI primitives | shadcn/ui (base-ui) |
| Package manager | pnpm |

## Misc

```bash
# Regenerate missing i18n translations via Ollama (default: es, zh-CN, ja)
uv run pixfabrica web gen-i18n web

# Type-check + build
pnpm build
```
