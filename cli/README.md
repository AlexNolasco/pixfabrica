# pixfabrica CLI

Command-line interface for rendering Pixfabrica composition JSON files to video.

Composition JSON uses **`clip_type`** and **`clips`** on each track (see [Architecture](../docs/ARCHITECTURE.md#terminology-composition-model)).
Examples under `cli/examples/` follow that wire format.

## Quick start

```bash
# Install all workspace packages
uv sync --all-packages

# Render the hello-world example (outputs output.mp4)
uv run pixfabrica render cli/examples/hello_world.json

# Custom output path
uv run pixfabrica render cli/examples/hello_world.json -o my_video.mp4
```

## Render command

```
pixfabrica render GRAPH [OPTIONS]
```

`GRAPH` may be a graph JSON file or a portable `.pixfabrica.zip` bundle exported from the web UI.

| Option | Description |
|---|---|
| `-o, --output PATH` | Output video path (default: `output.mp4`) |
| `--width INT` | Override output width |
| `--height INT` | Override output height |
| `--fps FLOAT` | Override frame rate |
| `--locale TEXT` | Locale for error messages, e.g. `en`, `es` (auto-detected from system) |

The graph JSON carries all job configuration (tracks, sounds, colors, typography). The CLI options only override resolution and frame rate — useful for quick low-res previews:

```bash
# Fast 360p preview
uv run pixfabrica render job.json --width 640 --height 360 --fps 12
```

## Plugin commands

```bash
# Scaffold a new plugin package
uv run pixfabrica plugin new my-effect

# List all installed plugins and their clip types
uv run pixfabrica plugin list --clip-types

# Generate NLS locale file for a plugin
uv run pixfabrica plugin gen-nls plugins/std

# Generate UI control mapping (schema.ui.generated.json) + bootstrap overrides
uv run pixfabrica plugin gen-ui plugins/std

# Fail CI if any field still maps to kind=unknown (after improving inference / overrides)
uv run pixfabrica plugin gen-ui plugins/std --check
```

## Font commands

Manage bundled fonts under `assets/fonts/` (manifest + `.ttf` sources + generated `.woff2` previews for the web UI and `GET /fonts`).

See [`assets/fonts/README.md`](../assets/fonts/README.md) for setup (drop licensed font files, then build).

```bash
# Validate manifest and generate .woff2 siblings from .ttf sources
uv run pixfabrica fonts build

# CI: fail if manifest is invalid or .woff2 previews are missing/stale (sources optional)
uv run pixfabrica fonts check

# Print resolved catalog (manifest + optional PIXFABRICA_FONTS_DIR extras)
uv run pixfabrica fonts list
uv run pixfabrica fonts list --json
```

```
pixfabrica fonts build [OPTIONS]
pixfabrica fonts check [OPTIONS]
pixfabrica fonts list [OPTIONS]
```

| Option | Commands | Description |
|---|---|---|
| `--fonts-dir PATH` | build, check, list | Bundled fonts directory (default: `assets/fonts`) |
| `--manifest PATH` | build, check | Path to `manifest.json` (default: `{fonts-dir}/manifest.json`) |
| `--dry-run` | build | Report missing/stale woff2 without writing files (same rules as `check`) |
| `--force` | build | Regenerate all woff2 even when up to date |
| `-v, --verbose` | build, check | Log each file action |
| `--json` | list | Emit catalog JSON (stdout) |

## Error codes

All errors are reported with a localised message. The underlying codes are:

| Code | Meaning |
|---|---|
| `unknown_plugin` | A `clip_type` in the JSON has no installed plugin (error code rename planned) |
| `invalid_parameter` | JSON fails schema validation (wrong type, out of range, missing field) |
| `missing_asset` | JSON file not found, or referenced audio/image asset is missing |
| `ffmpeg_failure` | FFmpeg encoding exited with a non-zero code |
| `analysis_failed` | Audio analysis (librosa) failed |
| `cancelled` | Render was interrupted by Ctrl+C |
| `output_write_error` | Cannot create or write the output file |
