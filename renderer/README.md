# pixfabrica-renderer

Python render engine. Not called directly — use the CLI (`pixfabrica render`) or API as the entry point.

## Quick start

```bash
uv sync --all-packages
uv run pytest renderer/tests
```

## Backends

| Backend | Used for |
|---|---|
| **Skia CPU** (skia-python) | Text, paths, shapes, waveforms, 2D drawing |
| **ModernGL GPU** (moderngl + GLSL shaders) | Gradients, particles, blur/glow, post-effects |

Video frames are pre-decoded via PyAV to GPU textures for O(1) per-frame lookup. FFmpeg handles final encoding (NVENC / VAAPI / VideoToolbox when available, CPU fallback otherwise).
