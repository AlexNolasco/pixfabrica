"""Real render/encode coverage for the parent-to-worker handoff."""

import av
import numpy as np
import pytest

from pixfabrica_core.clips import RenderJob
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_renderer.render import render_job
from pixfabrica_std.background.solid_background import SolidBackground
from pixfabrica_std.config.basic_themes import BasicThemes
from pixfabrica_std.text.static_text import StaticText


@pytest.mark.ffmpeg
@pytest.mark.parametrize("scenario", ["theme", "output_typography"])
async def test_serial_and_spawned_workers_use_resolved_settings(tmp_path, monkeypatch, scenario):
    # Limit process count without replacing the real pool or worker implementation.
    monkeypatch.setattr("pixfabrica_renderer.render.os.cpu_count", lambda: 4)
    register_clip_type(SolidBackground)
    register_setting_type(BasicThemes)
    register_clip_type(StaticText)
    frames = []
    for strategy in ("single", "multi"):
        data = {
            "title": "Worker parity",
            "description": "resolved theme",
            "width": 64,
            "height": 64,
            "fps": 24,
            "duration": 3,
            "parallelism": strategy,
            "video_encoder": "cpu",
            "theme": {
                "setting_type": "std-basic-themes",
                "id": "theme",
                "theme": "amber",
                "variant": "light",
            },
            "tracks": [
                {
                    "clip_type": "std-skia-track",
                    "id": "track",
                    "clips": [{"clip_type": "std-solid-background", "id": "bg"}],
                }
            ],
        }
        output_width = None
        output_height = None
        if scenario == "output_typography":
            data.update(width=640, height=540)
            data.pop("theme")
            data["tracks"][0]["clips"].append(
                {
                    "clip_type": "std-static-text",
                    "id": "text",
                    "text": "Worker typography",
                }
            )
            output_width = 320
            output_height = 270
        job = RenderJob.model_validate(data)
        output = tmp_path / f"{strategy}.mp4"
        events = [
            event
            async for event in render_job(job, output, width=output_width, height=output_height)
        ]
        assert any(event.parallelism_effective == strategy for event in events)
        with av.open(str(output)) as container:
            frames.append(next(container.decode(video=0)).to_ndarray(format="rgb24"))
        if scenario == "output_typography":
            assert len(np.unique(frames[-1].reshape(-1, 3), axis=0)) > 10
    np.testing.assert_allclose(frames[0].astype(float), frames[1].astype(float), atol=2)
