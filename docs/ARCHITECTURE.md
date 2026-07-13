# Pixfabrica Architecture

## Project Overview

**Pixfabrica** (pixel + fábrica/factory) is a programmatic video generation platform — the timeline-compositor equivalent of Shotstack/Creatomate. The core differentiator is composable clips and tracks (not just parameterized templates) combined with a plugin marketplace.

This is a full rewrite of a prior system (`video_maker`) that used Puppeteer + TypeScript + Canvas2D. That approach was too slow, lacked a composable timeline model, had tightly coupled plugins, and was not SaaS-ready.

---

## Primary Use Case — Music Visualization Kidbashing

The **core design center** is **kidbashing for music visualizations**: users assemble pre-built animated plugins the way a modeler bashes Gunpla kits — picking, stacking, and lightly tuning rather than hand-crafting animations. The timeline is a composition surface, not a programming environment for non-developer users.

**Design implications:**
- Plugins ship as **self-contained, predefined animations** — they produce a result with just an audio bus connected and sensible defaults applied. No assembly required beyond dropping them on the timeline.
- **Shader-based plugins (wgpu-py / WGSL) are preferred** for visual flair; they integrate with theme color tokens for reactive, music-synced visuals. Skia is slower and used primarily for text rendering.
- Plugins expose parameters appropriate to their complexity — no artificial limit — but defaults must work out-of-the-box without tuning.
- Plugins support **inheritance, dependencies, and localization** (`schema.nls.json` via `pixfabrica plugin gen-nls`).
- A **CLI scaffolding tool** (`pixfabrica plugin new`) bootstraps new plugins; keep it current with the latest plugin contract.
- Architecture is SaaS-grade and open-source-ready by design.

**Do not over-engineer toward Creatomate-style detail work** (per-frame keyframing, complex timeline editors, fine-grained compositing controls). When in doubt, bias toward fewer knobs and more opinionated defaults.

---

## Terminology (composition model)

The timeline compositor uses **clip** vocabulary in JSON and developer APIs.
Wire keys are namespaced by kind: `clip_type`, `effect_type`, `setting_type`, `sound_type`.

| Term | Meaning |
|---|---|
| **Plugin** | Installable Python package under `plugins/` |
| **ClipType** | A renderable type (`Cloud`, `StarNestGL`); subclass of `ClipSkia` / `ClipGL` |
| **Clip** | A placed instance on a track (`track.clips[]`); identified by `id`, typed by `clip_type` |
| **Track** | Timeline row that owns an ordered `clips` list and composites them |
| **Effect** | Per-clip or per-track image effect; keyed by `effect_type` in wire JSON |
| **Project setting** | Job-level theme/typography config; keyed by `setting_type` (`theme`, `typography_setting`) |
| **Sound** | Timeline audio source; keyed by `sound_type` (`std-sound`) |

**Composition JSON** (CLI, API jobs, web export) uses `clip_type` and `clips` for tracks and visual clips.
**`clip_type` strings** (e.g. `std-cloud`) are stable IDs — class renames do not change them.

Phased renames (see `feature/naming`):

1. Wire format + core models: `clips`, `clip_type`, `Clip` base class
2. Renderer bases: `ClipSkia`, `ClipGL` (done)
3. Project settings: `projectSettings` in the web store (done)
4. NLS/UI keys: `clip.*`, `effect.*`, `setting.*` prefixes (done)
5. Scaffold, folder names, purge legacy terms (done: `pixfabrica_core.clips`, `pixfabrica_core.composition`)

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend API | FastAPI (Python) |
| Shared models | Pydantic — `pixfabrica-core` workspace package |
| Renderer (2D) | skia-python — text, paths, shapes, waveforms |
| Renderer (GPU) | wgpu-py — WGSL shaders, particles, blur/glow/effects |
| Video decode | PyAV — pre-decode video frames to GPU textures |
| Video encode | FFmpeg — hardware accel: NVENC / VAAPI / VideoToolbox |
| CLI | Python + typer — accepts graph JSON, outputs video.mp4 |
| Plugins | Independent Python packages under `plugins/` |

---

## Web UI

**The timeline is king.** React Flow has been removed — there is no DAG graph editor in the UI.

### Web stack

| | |
|---|---|
| Framework | React 19 + TypeScript + Vite |
| UI primitives | shadcn/ui built on **base-ui** (not Radix) — `asChild` prop does not exist |
| Styling | Tailwind CSS v4 |
| State | Zustand + Zundo (undo/redo) |
| Timeline | `@xzdarcy/react-timeline-editor` |
| Drag/drop | `@dnd-kit/core` + `@dnd-kit/sortable` |
| Icons | lucide-react |
| Package manager | **pnpm** — never use npm or yarn in this project |

UI copy lives in `web/src/lib/i18n.messages.json` (English + locales). From repo root: `uv run pixfabrica web gen-i18n web` fills missing translations via Ollama (default `--lang es,zh-CN`; use `--lang ja` to add Japanese only; `--lang ""` rewrites JSON without calling Ollama). Edit English strings in the JSON (or add keys there), then re-run. `src/lib/i18n.ts` imports that file and exports `useT` / `TranslationKey`.

React Flow (`@xyflow/react`) was removed. Do not re-add it.

### UI philosophy — "Don't Make Me Think"

- **Start empty.** Panels that have nothing to show should be collapsed or hidden by default.
- **Reveal on intent.** The right (Properties) panel is collapsed by default and auto-opens when the user selects something.
- **Presets over raw inputs.** FPS, duration, and resolution use dropdowns with descriptive labels. Custom inputs only appear when the user explicitly requests them.
- **No orphan UI.** Don't render sections, labels, or buttons that have no effect yet. A placeholder with a hint ("Add one via Add Track → Audio") is better than an empty panel with a heading.

### Layout (4 panels)

```
┌─────────────┬───────────────────────┬──────────────────┐
│ Left        │ Preview               │ Properties       │
│ Project     │                       │ (collapsed until │
│ settings +  ├───────────────────────┤  something is    │
│ audio buses │ Timeline              │  selected)       │
└─────────────┴───────────────────────┴──────────────────┘
```

| Panel | Role |
|---|---|
| Left | Project settings (FPS, duration, resolution) + Audio Buses list. Not a plugin browser. |
| Center-top | Preview frame canvas |
| Center-bottom | Timeline |
| Right | `PropertiesPane` — parameters for the selected track or clip. Starts collapsed; auto-opens on first selection. Does not auto-close on deselect. |

Panel collapse state is driven by selection, not persisted to localStorage.

### Timeline interaction model

- **Tracks are rows.** Each track has a track-span action (movable/resizable) plus clip sub-rows.
- **Collapsed by default.** Clicking the chevron on a track label expands it to reveal clip sub-rows beneath (indented, visually distinct). Expand state is ephemeral UI state — not persisted.
- **Track types are chosen upfront** when adding a track: "Add Skia Track", "Add GL Track". Skia tracks only accept Skia clips; GL tracks only accept GL clips. The "Add Track" button is a dropdown.
- **Adding clips:** "+" button on an expanded track opens a visual plugin picker modal filtered by track type. The picker is a browsable catalog — NOT a search box — to preserve the kidbashing feel of discovering and trying plugins quickly.
- **Clip sub-rows** behave like clips: resizable within the track span bounds. `track.clips` stays compositor order (index `0` = back); the timeline shows **front-most at the top**, matching Properties draw order. Up/down on sub-rows adjusts z-order within the track.
- **Audio tracks** appear as timeline rows (not expandable — no visual clips inside). They have a movable/resizable span, audio-specific properties in `PropertiesPane`, and render a waveform pattern inside the action via `getActionRender`. Waveform peak data comes from the audio plugin API (`GET /plugins/{id}/waveform`; mock data acceptable for now).
- **Track list order in state** — `projectStore.tracks` is stored in **compositor order**: index `0` is painted first (rearmost), the last index is painted last (front-most). `toGraphJSON` iterates this same order, so **no extra reversal is needed when submitting a render job**.
- **Timeline UI** — rows are shown **front-most track at the top** (reversed relative to the array). New tracks are still **appended** in the store, so they appear at the **top** of the timeline and remain the front layer until reordered.
- Overlapping clips on the same track are intentional (stacking) — the old overlap warning has been removed.

#### Row ID conventions

| Row type | `row.id` format | `action.id` format |
|---|---|---|
| Track span | `{trackId}` | `{trackId}::span` |
| Clip sub-row | `{trackId}::clip::{clipId}` | `{clipId}` |

Use `parseClipRowId(rowId)` to extract trackId from clip sub-rows.

### State — projectStore

- `Track.trackType?: 'skia' | 'gl' | 'audio'` — optional for backwards compat, defaults to `'skia'`
- `toGraphJSON` maps `trackType` to the correct renderer track clip type (`std-skia-track`, `std-gl-track`, `std-audio-track`)
- `loadProject` defaults missing `trackType` to `'skia'`
- Undo history tracks only `meta`, `tracks`, `projectSettings` — not ephemeral UI state like selection or theme. **Edit → Undo/Redo** and **⌘/Ctrl+Z**, **⌘/Ctrl+⇧+Z**, and **Ctrl+Y** (redo on Windows) run `projectUndo` / `projectRedo`, which clear `selection` after each step. History entries are only recorded when that slice **changes** (value compare via `JSON.stringify`), so selection-only updates do not consume an undo step. `loadProject` / `resetProject` clear the undo stack.

### Internationalization

The app targets **English, Spanish (`es`), and Chinese Simplified (`zh-CN`)** — `UiLocale` is already defined in the store and wired into `AppSettings`.

**Rules for all new UI strings:**
- Never hardcode user-facing strings as bare literals in JSX. Write them so they can be extracted later — use named constants or a `t()` call when the i18n library is wired up.
- Avoid idioms or abbreviations that don't translate cleanly (e.g. prefer "Disable" over "Mute", "Remove" over "Nuke").
- Date/number formatting: use `Intl` APIs, never manual string concatenation.
- Plugin UI labels come from `schema.nls.json` (generated by `pixfabrica plugin gen-nls` via Ollama) — do not hardcode plugin param labels in the frontend.

### What NOT to build (web)

- No React Flow or DAG graph editor — removed entirely (`@xyflow/react` should be uninstalled).
- No drag-from-panel onto timeline sub-rows (fiddly); use the "+" picker instead.
- No always-visible clip sub-rows; collapsed-by-default keeps the timeline clean.

### Known gotchas (web)

- `DropdownMenuTrigger` (base-ui) does not accept `asChild` — style the trigger directly instead of wrapping a `<Button>`.
- `pnpm run build` catches TypeScript errors before the dev server does — run it after significant changes.
- The timeline library row height is fixed at `32px` — keep all label rows (`TrackLabel`, `ClipLabel`) at exactly `h-8` to maintain scroll sync.

---

## Project Structure

```
core/         → pixfabrica-core: shared Pydantic models (RenderJob, TrackClip, VisualClip, SoundClip, GraphNode, etc.)
web/          → React SPA (timeline editor, no rendering)
api/          → FastAPI (job queue, plugin discovery, render trigger)
renderer/     → Python render engine
plugins/      → independent Python packages
cli/          → typer CLI: render graph.json → video.mp4
```

---

## Timeline composition

- The editor is **timeline-first**: tracks contain ordered visual clips; sounds and project settings sit alongside.
- Each track is a `TrackClip` subclass (`SkiaTrack`, `GLTrack`, …) with a `clips[]` list.
- Clips reference plugin types via stable wire IDs (`clip_type`, `effect_type`, `setting_type`, `sound_type`).
- The legacy **DAG graph** model (`Graph`, `GraphNode`) remains in core for validation helpers and compose tooling.
- Composition JSON is the single wire format for web, API jobs, and CLI.

---

## Legacy node graph (DAG)

- Graph is a **DAG**, evaluated via topological sort
- Each `GraphNode` receives inputs from upstream outputs
- Graph nodes return a dict of named outputs (`{ "video": texture }`, `{ "value": 0.8 }`, etc.)
- **Textures stay on GPU** the entire pipeline — pixels read only once at FFmpeg pipe
- Graph serializes to JSON — same format used by web client, API jobs, and CLI

---

## Clip categories (timeline)

| Category | draw() | prepare() | Role |
|---|---|---|---|
| Sound clips | — | Pre-compute FFT for all frames, publish to audio bus | audio bus data |
| Visual clips | Called every frame | Allocate textures, load assets | canvas pixels |
| Math/Logic clips | — | — | scalars |
| Track clips | Owns canvas, children render into it | Layout rects | composite + transitions |

**Track clips** apply transitions (fade/slide/wipe) to their entire buffer. Child clips render into the track's layout regions.

**Sound clips** have a `start_time` — silence is padded before that point. No direct wiring to visual clips; they publish to named audio buses.

---

## Rendering Loop

```python
# SETUP (once per job)
sound_clips  → prepare() → audio_timeline dict (all frames pre-analyzed)
visual_clips → prepare() → allocate textures, load assets

# PER-FRAME LOOP
for frame in total_frames:
    audio_buses = { bus: audio_timeline[bus][frame] }
    for clip in visual_clips:  # track order + clip order within each track
        clip.draw(ctx, t, inputs, audio_buses)
    ffmpeg.stdin.write(fbo.read_pixels())
```

---

## Audio Bus System

- Audio analyzer clips publish to **named buses** (not wired directly to consumers)
- Each bus carries: `{ freq_data, bass, mid, high, beat, amplitude }`
- Visual clips subscribe by bus name via a `bus_select` dropdown widget in the UI
- **Explicit wiring** is only used when math/logic is needed between audio and a consumer
- `start_time` on sound clips → silence padded before that point in the timeline

---

## Plugin System

- Each plugin is a **standalone Python package**
- Exposes `schema.json` defining: params, input port types, output port types
- Optional pre-built JS bundle (`ui/dist/index.js`) for custom clip UI (legacy graph editor)
- Simple plugins need **zero frontend code** — client auto-generates clip property UI from schema
- Port types enforce valid connections (e.g. `audio` → `audio` only, `texture` → `texture`)

---

## Theme System

- Theme travels **with the job** (not a clip) — enables multi-tenant / white-label
- Clips reference theme tokens by name (`"primary"`, `"accent"`) — never raw colors
- **Theme generator project settings** run once in the `prepare` phase (before render loop):
  - `image_palette` — extract palette from album art / image
  - `spotify` — pull from track metadata
  - `ai_theme` — generate from mood/genre description prompt
- `ThemeSetting` plugins supply the project palette; typography uses `TypographySetting`

---

## Rendering by clip type

| Clip kind | Tool |
|---|---|
| Gradient backgrounds | WGSL fragment shader (wgpu-py) |
| Marquee / scrolling text | skia-python (replaces GSAP + DOM) |
| Rain / particles | wgpu-py instanced rendering |
| Waveform band visualizer | skia-python (clip + path) |
| Video playback | PyAV pre-decode all frames → GPU textures, O(1) lookup per frame |
| 2D shapes / paths | skia-python |
| Blur / glow / post-effects | WGSL fragment shaders (wgpu-py) |

---

## SaaS / Server Rendering

- Client designs graph → saves JSON
- `POST /jobs` with graph JSON → queued render job
- WebSocket streams render progress back to client
- GPU server recommended (AWS g4dn / GCP T4) but CPU fallback works (Skia CPU mode)
- Same graph JSON drives: web preview, API jobs, CLI batch rendering
- **Key differentiators vs Shotstack/Creatomate:**
  - Composable clip timeline (not just parameterized templates)
  - Plugin marketplace — third-party clips with custom UI
  - Audio-reactive built-in (audio bus system)
  - Theme system for white-label / multi-tenant

---

## Naming

- **Pixfabrica** = pixel + fábrica (factory/forge in Spanish/Portuguese)
- Tone: developer-first, production-grade, composable
