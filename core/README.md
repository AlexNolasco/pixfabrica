# pixfabrica-core

Shared Pydantic models and types used across the renderer, API, CLI, and plugins. No rendering logic lives here.

## Quick start

```bash
uv sync --all-packages
uv run pytest core/tests
```

## What's exported

| Area | Key types |
|---|---|
| Legacy DAG graph | `Graph`, `GraphNode`, `PortType`, `PortConnection`, `topological_sort` |
| Clips (plugin authoring) | `ClipSkia`, `ClipGL`, `RenderContext`, `ClipTypeProtocol` — import from `pixfabrica_core.clips` |
| Audio bus | `AudioBusFrame`, `AudioTimeline`, `SoundClip`, `AudioVisualMixin` |
| Plugin protocol | `PluginManifest`, `PluginProtocol`, `DrawableProtocol` |
| Theme / color | `ColorPalette`, `VisualClip` |
| Errors | `RenderError`, `RenderErrorCode` |
| Utilities | `EasingType`, `apply_easing`, `RenderProgress` |

## As a dependency

```toml
# pyproject.toml
[tool.uv.sources]
pixfabrica-core = { workspace = true }
```
