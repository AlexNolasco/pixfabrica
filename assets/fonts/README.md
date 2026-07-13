# Bundled fonts

Ship **`.ttf` / `.otf`** sources here for Skia and **`.woff2`** siblings for the web UI (`preview_url`).

## Setup

1. Add font files matching `manifest.json` (e.g. `Inter-Regular.ttf`).

   **Inter 4.1** — the zip root only has variable fonts (`InterVariable.ttf`). Static `.ttf` files are under `extras/ttf/`:

   - `Inter-Regular.ttf` (400)
   - `Inter-Medium.ttf` (500)
   - `Inter-Bold.ttf` (700)

   Copy those three into this folder (`assets/fonts/`).

   **JetBrains Mono 2.x** — static `.ttf` is under `fonts/ttf/`:

   - `JetBrainsMono-Regular.ttf`

   Copy into this folder (`assets/fonts/`).

   **Museo Moderno** ([Google Fonts](https://fonts.google.com/specimen/Museo+Moderno), **SIL OFL 1.1**) — rounded display sans, safe to bundle. Included in this repo:

   - `MuseoModerno-Regular.ttf`, `MuseoModerno-Medium.ttf`, `MuseoModerno-Bold.ttf` + `OFL-MuseoModerno.txt` (from [google/fonts](https://github.com/google/fonts/tree/main/ofl/museomoderno))

   **Noto Sans CJK JP** ([notofonts/noto-cjk](https://github.com/notofonts/noto-cjk), **SIL OFL 1.1**) — Japanese (and shared CJK glyphs). Included for gallery starters and JP typography:

   - `NotoSansCJKjp-Regular.otf`, `NotoSansCJKjp-Bold.otf` + `OFL-NotoSansCJK.txt` (from `Sans/OTF/Japanese/`)

   Use this as the reference for adding other OFL families.

2. From the repo root, **build** preview files, then **check**:

   ```bash
   uv run pixfabrica fonts build   # .ttf → .woff2 (required once after adding sources)
   uv run pixfabrica fonts check   # CI: verifies .woff2 exist and are fresh
   ```

   `fonts check` looks for `.woff2`, not `.ttf`. If you only copied `.ttf` files, run `build` first.

3. Commit both sources and generated `.woff2` files, or run `fonts build` in CI before release.

## Optional extra directory

Set `PIXFABRICA_FONTS_DIR` to a folder of additional upright `.ttf` / `.otf` files. They are merged into `GET /fonts` at runtime (manifest entries win on `id` collision).

## Licenses

Only add fonts you are **allowed to redistribute** (ship in the repo and serve via `GET /fonts`).

| Source | Safe to bundle? |
|---|---|
| [Google Fonts](https://fonts.google.com/) (OFL / Apache) | Usually yes — read the license on each family |
| Inter, JetBrains Mono (official releases) | Yes, per their licenses |
| [DaFont](https://www.dafont.com/) | **Often no** — many are “personal use only”, demo, or unknown. Check the badge on the font page and the readme inside the zip. |

**Example — [Varsity on DaFont](https://www.dafont.com/varsity-2.font):** personal use / unclear rights — use **[Museo Moderno](https://fonts.google.com/specimen/Museo+Moderno)** or another OFL family from Google Fonts instead.

Prefer **SIL Open Font License (OFL)** or fonts with explicit commercial + redistribution terms.

## Adding a font

### Option A — Bundled (manifest, for fonts shipped with the app)

Worked example: **Museo Moderno** (already in `manifest.json`).

1. Download from an official source (e.g. `ofl/museomoderno/` in [google/fonts](https://github.com/google/fonts)). Copy the static `.ttf` files and license file (`OFL.txt`) here.

2. Add an entry to `manifest.json` (family name must match font metadata — for Museo Moderno it is `"MuseoModerno"`):

   ```json
   {
     "id": "museo-moderno",
     "family": "MuseoModerno",
     "label": "Museo Moderno",
     "category": "sans",
     "weights": [
       { "value": 400, "source": "MuseoModerno-Regular.ttf" },
       { "value": 500, "source": "MuseoModerno-Medium.ttf" },
       { "value": 700, "source": "MuseoModerno-Bold.ttf" }
     ]
   }
   ```

   - `id` — stable slug (URLs / keys)
   - `family` — internal family name Skia uses
   - `source` — filename in this directory
   - `category` — `"sans"` or `"mono"`

3. Build and check:

   ```bash
   uv run pixfabrica fonts build
   uv run pixfabrica fonts check
   ```

### Option B — Local extra dir (try a font without editing the manifest)

For one-off or licensed fonts you do **not** want in git:

1. Create a folder, e.g. `C:\pixfabrica-fonts\`
2. Drop upright `.ttf` / `.otf` files there (one file per weight).
3. Set env and restart the API:

   ```bash
   export PIXFABRICA_FONTS_DIR=/c/pixfabrica-fonts
   ```

   Scanned fonts appear in `GET /fonts` alongside manifest entries. Generate `.woff2` previews yourself or copy them next to the `.ttf` with the same basename if the web UI needs them.

Manifest entries **win** on `id` collision with scanned extras.

### Option C — Web app upload (Typography panel)

In the editor, open **Typography** → check the redistribution confirmation → **Install font…**. Upload a single `.ttf` / `.otf` or a `.zip` of upright faces (32 MB max). The API stores sources under **`user-fonts/`** (or `PIXFABRICA_USER_FONTS_DIR`), builds `.woff2` previews, and merges the family into `GET /fonts`.

Custom fonts used in typography are included in **project bundle export** under `assets/fonts/` and re-installed on **import**.

### Removing uploaded fonts (manual)

There is no delete action in the web UI yet. To remove user-installed fonts:

1. Stop the API (optional but avoids stale catalog entries while editing).
2. Delete the `.ttf` / `.otf` and matching `.woff2` files from:
   - **`user-fonts/`** in the API working directory (default), or
   - **`PIXFABRICA_USER_FONTS_DIR`** if you set it
   - Fonts dropped in **`PIXFABRICA_FONTS_DIR`** are separate — remove them there if you added files manually
3. Restart the API (or trigger a catalog refresh) so `GET /fonts` matches disk.

Bundled manifest fonts under `assets/fonts/` are not affected.
