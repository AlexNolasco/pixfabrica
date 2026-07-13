# pixfabrica-std-effects

Per-clip **GLEffect** and **SkiaEffect** plugins. Kept separate from `pixfabrica-std` so effect dependencies stay optional, but this package stays lightweight (no torch / diffusers).

Raster and AI effects (e.g. FLUX img2img) live in the optional sample plugin **`pixfabrica-std-effects-sample`** — see `plugins/README.md`.

## Install

From the monorepo root (included in default dev sync):

```bash
uv sync --all-packages
```

## Disable

If you do not need per-clip GL/Skia effects, disable the plugin in `pixfabrica.toml` at the repo root:

```toml
[plugins]
disabled = ["pixfabrica-std-effects"]
```

Disabled plugins are omitted from the effect catalog picker. Existing jobs that reference those `effect_type` values deserialize as no-op unknown effects.

## Authoring

Add new effects under `src/pixfabrica_std_effects/effects/` and register them on `Plugin.effects` in `__init__.py`. Keep this package GL + Skia only — heavy AI deps belong in external sample/community plugins.
