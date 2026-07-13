# Pixfabrica Plugins

This directory contains Pixfabrica plugins. `std/` is the built-in standard library; `std_effects/` holds lightweight GL/Skia per-clip effects. Raster/AI effects are optional sample/community plugins. Community plugins are installed here by cloning their repository.

## Terminology

Pixfabrica uses a small vocabulary.
Use the right term for your audience.

| Term | Audience | Meaning |
|---|---|---|
| **Plugin** | Everyone | Installable package (e.g. `pixfabrica-std`) |
| **ClipType** | Developers | Renderable type a plugin registers (e.g. `Cloud`, `StarNestGL`); Python class subclassing `ClipSkia` / `ClipGL` |
| **Clip** | Developers + users | Placed instance on a track in code and project JSON (`track.clips[]`); references a ClipType via `clip_type` (e.g. `std-cloud`) |
| **Project setting** | Users | Project-level config (theme, typography); wire fields `theme` and `typography_setting` |

**Wire format (composition JSON):**

- Tracks and visual clips use **`clip_type`** (stable ID string, e.g. `std-cloud`).
- Each track has **`clips`**: an ordered list of placed visual clips (compositor order: index `0` = back).
- **Effects** use **`effect_type`**; project settings use **`setting_type`**; sounds use **`sound_type`**.

**Naming rules for plugin authors:**

- ClipType implementation files and classes should use short nouns (`cloud.py` / `Cloud`), not redundant suffixes.
- **`clip_type` IDs are stable public identifiers** — do not rename them when refactoring class names.
- Register clip types on `Plugin.clip_types`.

---

## Installing a community plugin

Plugins are separate git repositories cloned under `plugins/`. Development always assumes a full Pixfabrica checkout (core, renderer, API, etc.) — install the plugin into the **repository root** `.venv`, not an isolated environment.

```bash
# From the Pixfabrica repository root
git clone https://github.com/someone/pixfabrica-rain plugins/pixfabrica-rain

# Register the plugin and its dependencies in the shared environment
uv add --editable ./plugins/pixfabrica-rain --no-workspace
```

That's it. `pixfabrica plugin list` will pick it up on next run. Use `--no-workspace` so uv does not treat the plugin as a workspace member (which conflicts with the plugin's `path = "../../core"` source on `pixfabrica-core`). You do not need to add the plugin to `[tool.uv.workspace] members`.

**Reference PoCs** (gitignored in this monorepo — clone under `plugins/` and follow each README):

- [pixfabrica-std-sample](https://github.com/AlexNolasco/pixfabrica-std-sample) — community clip plugin scaffold
- [pixfabrica-std-effects-sample](https://github.com/AlexNolasco/pixfabrica-std-effects-sample) — singleton raster/AI effects (FLUX img2img); heavy deps isolated

---

## Authoring a plugin

### Directory structure

```
plugins/my-plugin/
├── pyproject.toml
└── src/
    └── my_plugin/
        ├── __init__.py     ← must expose a Plugin class
        └── my_clip.py
```

### `pyproject.toml`

```toml
[project]
name = "my-plugin"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "pixfabrica-core[audio]>=0.1.0,<1.0",
    "skia-python>=144.0.post2",  # if you ship Skia clips
]

[tool.uv.sources]
pixfabrica-core = { path = "../../core", editable = true }
```

`../../core` is correct when the plugin lives at `plugins/my-plugin/`. Pixfabrica is not published to PyPI — core is satisfied from the monorepo path.

Discovery is convention-based: a valid `pyproject.toml` + a `Plugin` class in the package `__init__.py`. No entry points required.

Scaffold a new plugin from the repo root:

```bash
uv run pixfabrica plugin new my-plugin -o plugins
```

### `__init__.py`

```python
from typing import ClassVar

from pixfabrica_core.plugins import PluginManifest

from my_plugin.my_clip import MyClip

class Plugin:
    manifest: ClassVar[PluginManifest] = PluginManifest(
        name="my-plugin",
        display_name="My Plugin",
        description="What this plugin does.",
        requires_core=">=0.1.0,<1.0",
    )
    clip_types: ClassVar[list[type]] = [MyClip]
```

### Defining a clip type

Subclass `Clip` (or `ClipSkia` / `ClipGL` for visual types) and set a unique `clip_type`. Add your params as Pydantic fields.

```python
from typing import ClassVar
from pixfabrica_core.clips import Clip

class MyClip(Clip):
    clip_type: ClassVar[str] = "my-plugin-my-clip"
    intensity: float = 0.5
    color: str = "#ffffff"
```

`clip_type` must be globally unique — prefix it with your plugin name to avoid collisions.

### Property field order

The Properties pane field order comes from **Pydantic declaration order** on each clip type
class. `gen-ui` reads `model_fields.keys()` — reorder fields in the clip model; do
not use `schema.ui.overrides.json` `sections` just to reorder.

Three blocks (full contract in `pixfabrica_core.plugin_layout`):

1. **Identity** — `bus_select` (if present, first) → content → appearance.
2. **Layout** — `offset_x → offset_y → padding_x → padding_y → width → height → angle → opacity`
   (subset only; `band_height` / `content_inset_x` occupy the `height` / `padding_x` slots).
3. **Tuning** — clip-specific params after layout.

Theme/config/job settings are out of scope. Effect clips without layout fields:
`bus_select` → effect params → tuning.

For shared **runtime** helpers (not UI order), std ships e.g. `pixfabrica_std.tilt`
for the `angle` numeric contract — optional for third-party plugins.

For clip types that render to the canvas, subclass `VisualClip` (via `ClipSkia` or `ClipGL`) and implement `draw()`:

```python
from pixfabrica_core.clips import ClipSkia, RenderContext

class MyVisualClip(ClipSkia):
    clip_type: ClassVar[str] = "my-plugin-my-visual"
    opacity: float = 1.0

    def draw(self, ctx: RenderContext) -> None:
        ...
```

### Transparency and compositing

Visual clips on a **GL track** share one offscreen framebuffer and paint in **clip order** (first = bottom, last = top). The renderer uses straight-alpha blending (`SRC_ALPHA`, `ONE_MINUS_SRC_ALPHA`). When authoring GL shaders and clips, **design for transparency from the start** — it is easy to accidentally paint opaque black over everything below.

**Fragment output (GL):** Prefer **straight alpha**: `frag_color = vec4(rgb, alpha)` where `rgb` is full-intensity color and `alpha` is coverage. Do **not** output opaque black with `alpha = 1` in “empty” regions — use `alpha = 0` (or luma-derived alpha for soft fades) so lower clips and partial-opacity overlays remain visible. Premultiplied output (`vec4(rgb * alpha, alpha)`) only works if you match the blend mode; the built-in GL path expects straight alpha.

**Fullscreen backgrounds:** Raymarched or procedural fills should fade alpha in dark areas (see `std-neon-tunnel-gl`), not fill the quad with `(0, 0, 0, 1)`. Otherwise lower clips cannot show through, and semi-transparent meshes only blend against black.

**Overlays (bars, frames, meshes):** Leave pixels untouched where you have nothing to draw (`alpha = 0`), same idea as `std-spectrum-bars`. For 3D meshes, blend over prior GL content without depth-buffer clears — use `draw_mesh_blend` in `pixfabrica_std.mesh.shader_helper`, not a depth-clear pass on top of 2D layers.

**`luma_alpha` (GL overlays):** When possible, expose a `luma_alpha` param on overlay-style GL clips (audio viz, lines, rays, meshes). Default **1.0** so dark / undrawn pixels stay transparent at full opacity; **0** treats the clip bounds as solid and can wipe layers below with opaque black. Shader pattern:

```glsl
float luma = dot(col.rgb, vec3(0.299, 0.587, 0.114));
float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
frag_color = vec4(col.rgb * u_opacity, alpha);
```

Use coverage-based alpha instead when luma is not meaningful (e.g. hard-edged bars — see `std-sweep-lines-gl`). **Background GL clips** (full-frame procedural fills) may omit `luma_alpha` if the effect is meant to cover the frame; still fade alpha in dark regions where appropriate (`std-neon-tunnel-gl`).

**Hand-off to Skia:** The FBO is read back with straight-alpha converted to premultiplied BGRA for Skia (`GLContext.to_skia_bitmap`). Partial-alpha pixels depend on correct GL alpha during the GL track pass.

Reference implementations: `plugins/std/src/pixfabrica_std/audio/spectrum_bars.py`, `audio/wavy_lines_gl.py`, `background/neon_tunnel_gl.py`, `background/heart_dance_gl.py`, `mesh/gltf_mesh_gl.py`, `renderer/src/pixfabrica_renderer/gl_context.py`.

### Stateless `draw()` contract

`draw(ctx)` MUST be a pure function of `self` (after `prepare()` has run),
`ctx.time.frame`, `ctx.bounds`, `ctx.canvas`, and `ctx.audio_bus_frame`.
It MUST NOT mutate any cross-frame state on `self` — no EMAs, no deques
of past beats, no "scroll position", no `_last_frame` markers, no BPM
accumulators. Calling `draw(F)` for any frame `F` in any order MUST
produce identical pixel output.

**Why:** when the job sets `parallelism = "multi"`, the renderer ships
frames out of order to a pool of worker processes. State accumulated
inside `draw()` is silently corrupted across workers and produces
visibly wrong output (jumpy bars, mis-aligned scrolls, lost beats). The
serial renderer happens to give the "expected" sequential semantics,
but stateful `draw()` is a latent bug under either strategy.

**How:** any temporal smoothing or look-ahead/look-back computation must
be **precomputed once in `prepare()`** for the entire job. `prepare()`
receives `ctx.audio: AudioTimeline` (full per-frame mel buses for every
sound) and `ctx.job.total_frames`, so audio-reactive clips can build a
per-frame lookup table (typically a `numpy.ndarray`) that `draw()` only
indexes into.

```python
import numpy as np
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipSkia, PrepareContext, RenderContext

class SmoothedBass(AudioVisualMixin, ClipSkia):
    clip_type: ClassVar[str] = "my-plugin-smoothed-bass"
    smoothing: float = 0.85

    _bass: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx, _bounds=None):
        total = ctx.job.total_frames
        frames = ctx.audio.get(self.bus_select) if self.bus_select else None
        history = np.zeros(total, dtype="f4")
        if frames:
            s = self.smoothing
            acc = 0.0
            for f in range(min(total, len(frames))):
                acc = acc * s + frames[f].bass * (1.0 - s)
                history[f] = acc
        self._bass = history

    def draw(self, ctx):
        idx = max(0, min(ctx.time.frame, self._bass.shape[0] - 1))
        bass = float(self._bass[idx]) if self._bass.size else 0.0
        # ...use `bass` to draw — no self.* mutation here.
```

`PrivateAttr` slots that are written **once** in `prepare()` (compiled
GL programs, baked Skia images, parsed lyrics, layout caches, decoder
handles, the per-frame lookup table itself) are fine — those are setup
artefacts, not per-frame state. The rule only forbids mutation in
`draw()`.

See `plugins/std/src/pixfabrica_std/audio/spectrum_bars.py` and
`audio_debug.py` for full reference implementations.

### Listing clip types

```bash
pixfabrica plugin list --clip-types
```

---

## Standard effects (`pixfabrica-std-effects`)

GL and Skia **per-clip effects** live in `plugins/std_effects/` (`pixfabrica_std_effects`). Split from `pixfabrica-std` so effect deps stay optional; this package stays lightweight.

```bash
uv sync --all-packages
```

Disable in `pixfabrica.toml` if you do not want GL/Skia per-clip effects:

```toml
[plugins]
disabled = ["pixfabrica-std-effects"]
```

**Raster / AI effects** (torch, diffusers, etc.) are not in this package. Clone [pixfabrica-std-effects-sample](https://github.com/AlexNolasco/pixfabrica-std-effects-sample) to `plugins/pixfabrica-std-effects-sample/` and `uv add --editable ./plugins/pixfabrica-std-effects-sample --no-workspace`.

See `plugins/std_effects/README.md`.

---

## Standard library (`pixfabrica-std`)

Built-in clip types and project settings. Lives under `plugins/std/`; the Python package is `pixfabrica_std` in `src/pixfabrica_std/`. Per-clip GL/Skia effects live in `std_effects`; raster/AI effects live in optional sample/community plugins.

```bash
# List all available clip types
pixfabrica plugin list --clip-types
```

### UI mapping: generated vs overrides

Run from the repo root:

```bash
uv run pixfabrica plugin gen-ui plugins/std
```

This **always overwrites** `src/pixfabrica_std/schema.ui.generated.json` (machine-owned). It **creates** `src/pixfabrica_std/schema.ui.overrides.json` as `{}` only if that file is missing — it **never** deletes your edits there.

**Workflow:** adjust Pydantic models → re-run `gen-ui` → resolve any new `unknown` hints → fix by improving `gen-ui` heuristics **or** by adding entries under **`schema.ui.overrides.json`**.

#### Merge rule (API or web)

At runtime, build the effective UI spec per `clip_type` (or `effect_type` / `setting_type` for non-clip catalog entries):

1. Start from `schema.ui.generated.json[clip_type]` (defaults from `gen-ui`).
2. Deep-merge `schema.ui.overrides.json[clip_type]` on top — **override wins** at every overlapping key.

Commit **`schema.ui.overrides.json`**; treat **`schema.ui.generated.json`** as optional in git (regenerate in CI or locally).

#### Override examples

Top-level keys are **type id** strings (`std-glow-text`, `std-gradient`, …). Under each type you may supply partial objects; only keys you set are merged.

**1. Tweak one control:**

```json
{
  "std-glow-text": {
    "controls": {
      "opacity": { "kind": "slider", "show_as": "fraction" }
    }
  }
}
```

**2. Add `custom_ui` for a whole clip panel:**

```json
{
  "std-gradient": {
    "custom_ui": {
      "entry": "gradientPanel",
      "bundle": "/plugins/std/ui/dist/gradient.js",
      "protocol": 1
    }
  }
}
```

**3. Replace sections** (full `sections` array replaces the merged `sections` — use only for a genuinely different section layout, **not** to reorder fields; set order on the Pydantic model instead):

```json
{
  "std-marquee": {
    "sections": [
      { "id": "content", "title_key": "ui.clip.std-marquee.section.content", "fields": ["text", "role", "align"] },
      { "id": "timing",  "title_key": "ui.section.timing", "fields": ["start", "duration", "enabled"] }
    ]
  }
}
```

#### `Literal[...]` and `StrEnum` labels

- **`StrEnum` / `Enum`:** `gen-ui` sets `label_key_prefix` to `enum.{ClassName}`; `gen-nls` emits `enum.{ClassName}.{wire}`.
- **`Literal["a", "b", ...]`:** `gen-ui` sets `label_key_prefix` to `clip.{clip_type}.field.{field}.option`. Each wire value gets an NLS key `{prefix}.{slug}` where slug is the value lowercased with spaces/punctuation normalized to underscores.

The web resolves the label as `nls[label_key_prefix + "." + slug(wire)]` with fallback to the raw wire string if missing.

#### Related files

| File | Role |
|------|------|
| `schema.ui.generated.json` | Output of `gen-ui`; do not hand-edit |
| `schema.ui.overrides.json` | Your presentation overrides; merged on top |
| `schema.nls.json` | Translations; output of `gen-nls` |

### Misc

```bash
# Generate NLS locale file for all clip types (requires Ollama)
uv run pixfabrica plugin gen-nls plugins/std

# Fail CI if any field still maps to kind=unknown
uv run pixfabrica plugin gen-ui plugins/std --check
```

