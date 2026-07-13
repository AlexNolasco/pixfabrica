# Clip preview audio samples

Checked-in bus timelines and trimmed audio for testing `bus_select` clips in the clip mini preview.

## Layout

```
preview-samples/
  sources.json       # bake inputs (id, label, file, sourceUrl, license)
  sources/           # original Pixabay mp3 files (committed)
  manifest.json      # baked catalog for web + API (generated)
  drums/             # audio.mp3 (45s) + timeline.npz
  symphony/
  ambient/
```

## Bake (after adding or changing sources)

From repo root, with `ffmpeg` on PATH:

```bash
# Copy drums.mp3, symphony.mp3, ambient.mp3 into sources/
# Edit sources.json with full Pixabay URLs and license notes in this README.

uv run pixfabrica web bake-preview-samples
```

Default: **45 seconds**, **StemAnalyzer** per source. Options:

- `pixfabrica web bake-preview-sample path/to/file.mp3` — single file (same defaults)
- `--all-loops` — also emit 8s / 15s / 45s variants (`drums-8s`, …)
- `--seconds 8` — one custom length

Restart the API after rebaking so timeline caches reload.

## Licenses

Document each track here (Pixabay Content License + page URL). `sources.json` carries short `sourceUrl` / `license` fields for tooling; this file holds the human-readable attribution.

| Sample   | Pixabay URL | Notes |
|----------|-------------|-------|
| drums    | (add link)  |       |
| symphony | (add link)  |       |
| ambient  | (add link)  |       |
