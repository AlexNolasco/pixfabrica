"""Contracts across the resolved render handoff, independent of transport."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.clips import JobInfo, RenderJob
from pixfabrica_core.composition.effect_registry import register_effect
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_renderer.parallel.snapshot import encode_render_snapshot, restore_render_snapshot
from pixfabrica_std.background.solid_background import SolidBackground
from pixfabrica_std.config.basic_themes import BasicThemes
from pixfabrica_std.config.default_typography import DefaultTypography
from pixfabrica_std.text.static_text import StaticText
from pixfabrica_std_effects.effects.tvbug_gl import TvbugGL


def _job_and_info():
    register_clip_type(SolidBackground)
    register_clip_type(StaticText)
    register_setting_type(BasicThemes)
    register_setting_type(DefaultTypography)
    register_effect(TvbugGL)
    job = RenderJob.model_validate(
        {
            "title": "Literal {AUTHOR}",
            "author": "Alice",
            "description": "Snapshot",
            "width": 640,
            "height": 540,
            "fps": 24,
            "duration": 10,
            "theme": {"setting_type": "std-basic-themes", "id": "theme", "theme": "amber"},
            "typography_setting": {
                "setting_type": "std-default-typography",
                "id": "fonts",
                "family": "Arial",
                "mono_family": "Consolas",
            },
            "sounds": [
                {
                    "sound_type": "std-sound",
                    "id": "sound",
                    "source": "unused.wav",
                    "bus": "main",
                    "start": 1,
                    "seek": 0.5,
                    "enabled": False,
                }
            ],
            "tracks": [
                {
                    "clip_type": "std-skia-track",
                    "id": "track",
                    "start": 5,
                    "duration": 5,
                    "effects": [
                        {
                            "effect_type": "std-tvbug-gl",
                            "id": "track-fx",
                            "opacity": 0.75,
                            "frequency": 14,
                        }
                    ],
                    "clips": [
                        {
                            "clip_type": "std-solid-background",
                            "id": "bg",
                            "start": 2,
                            "height": 0.5,
                            "effects": [
                                {
                                    "effect_type": "std-tvbug-gl",
                                    "id": "clip-fx",
                                    "opacity": 0.8,
                                    "frequency": 12,
                                }
                            ],
                        },
                        {
                            "clip_type": "std-static-text",
                            "id": "text",
                            "start": 1,
                            "text": "{TITLE} {UNRECOGNIZED}",
                        },
                    ],
                }
            ],
        }
    )
    info = JobInfo(
        title=job.title,
        description=job.description,
        width=320,
        height=270,
        fps=12,
        duration=10,
        colors=ColorPalette(),
        typography=job.typography.scale(0.5),
        locale="es",
        output_width=640,
        output_height=540,
    )
    return job, info


def test_snapshot_preserves_concrete_plugins_timing_and_resolved_values():
    job, info = _job_and_info()
    frame = AudioBusFrame.zero().model_copy(update={"amplitude": 0.75, "beat": True})
    audio = {"main": [frame]}
    snapshot = encode_render_snapshot(job, info, audio)
    restored = restore_render_snapshot(snapshot)
    track = restored.job.tracks[0]
    assert track.start == 5
    assert [clip.id for clip in track.clips] == ["bg", "text"]
    assert [clip.start for clip in track.clips] == [7, 6]
    assert [clip.duration for clip in track.clips] == [5, 5]
    assert isinstance(track.clips[0], SolidBackground)
    assert track.clips[0].height == 0.5
    assert isinstance(track.effects[0], TvbugGL)
    assert track.effects[0].effect_type == "std-tvbug-gl"
    assert track.effects[0].opacity == 0.75
    assert track.effects[0].frequency == 14
    assert isinstance(track.clips[0].effects[0], TvbugGL)
    assert track.clips[0].effects[0].opacity == 0.8
    assert track.clips[0].effects[0].frequency == 12
    assert isinstance(restored.job.theme, BasicThemes)
    assert restored.job.theme.theme == "amber"
    assert isinstance(restored.job.typography_setting, DefaultTypography)
    assert restored.job.typography_setting.family == "Arial"
    assert restored.job.typography_setting.mono_family == "Consolas"
    assert restored.job.sounds[0].sound_type == "std-sound"
    assert restored.job.sounds[0].start == 1
    assert restored.job.sounds[0].seek == 0.5
    assert (restored.info.width, restored.info.height, restored.info.fps) == (320, 270, 12)
    assert (restored.info.output_width, restored.info.output_height) == (640, 540)
    assert restored.info.locale == "es"
    assert restored.info.title == "Literal {AUTHOR}"
    assert restored.info.typography == info.typography
    assert restored.info.typography.body_medium.size == 7.25
    assert restored.job.typography.body_medium.size == 14.5
    assert restored.audio["main"][0].amplitude == 0.75
    assert restored.audio["main"][0].beat is True


def test_snapshot_does_not_repeat_variable_substitution_or_share_mutable_state():
    job, info = _job_and_info()
    audio = {"main": [AudioBusFrame.zero()]}
    snapshot = encode_render_snapshot(job, info, audio)
    text_clip = job.tracks[0].clips[1]
    assert isinstance(text_clip, StaticText)
    text_clip.text = "changed after capture"
    audio["main"][0].amplitude = 1
    restored = restore_render_snapshot(snapshot)
    restored_text = restored.job.tracks[0].clips[1]
    assert isinstance(restored_text, StaticText)
    assert restored_text.text == "Literal {AUTHOR} {UNRECOGNIZED}"
    assert restored.audio["main"][0].amplitude == 0
    assert restored.job.project_variable_warnings() == job.project_variable_warnings()
    assert restored.job.project_variable_warnings()[0].source == "UNRECOGNIZED"
    restored.job.tracks[0].clips[0].start = 99
    assert restore_render_snapshot(snapshot).job.tracks[0].clips[0].start == 7


def test_snapshot_rejects_project_files_and_unsupported_snapshot_versions():
    job, info = _job_and_info()
    with pytest.raises(ValidationError):
        restore_render_snapshot(job.model_dump_json())
    snapshot = encode_render_snapshot(job, info, {})
    with pytest.raises(ValidationError):
        restore_render_snapshot(snapshot.replace("resolved-render-v1", "resolved-render-v2"))


def test_snapshot_rejects_missing_plugin_with_original_wire_identifier():
    import json

    job, info = _job_and_info()
    payload = json.loads(encode_render_snapshot(job, info, {}))
    payload["job"]["tracks"][0]["effects"][0]["effect_type"] = "missing-plugin-effect"
    with pytest.raises(RenderError) as exc:
        restore_render_snapshot(json.dumps(payload))
    assert exc.value.code == RenderErrorCode.UNKNOWN_PLUGIN
    assert exc.value.context == {"effect_type": "missing-plugin-effect"}


def test_snapshot_retains_effective_palette_separately_from_authored_defaults():
    job, info = _job_and_info()
    from pixfabrica_std.config.basic_themes import get_named_palette

    info = replace(info, colors=get_named_palette("amber", "light"))
    restored = restore_render_snapshot(encode_render_snapshot(job, info, {}))
    assert restored.info.colors.model_dump(mode="json") == info.colors.model_dump(mode="json")
    assert restored.info.colors.model_dump(mode="json") != restored.job.colors.model_dump(
        mode="json"
    )


async def test_spawned_worker_preserves_nonzero_timing_for_out_of_order_frames():
    """Exercise spawn, plugin registration, restoration, prepare, and real pixels."""
    from pixfabrica_core.clips import PrepareContext, TimeState
    from pixfabrica_core.theme.color import ColorToken
    from pixfabrica_renderer.compositor import Compositor
    from pixfabrica_renderer.parallel import ProcessWorkerPool
    from pixfabrica_renderer.parallel.protocol import FrameDone, FrameRequest

    job, info = _job_and_info()
    # This check needs a deterministic Skia scene, without a GPU dependency.
    job.tracks[0].effects.clear()
    job.tracks[0].clips = job.tracks[0].clips[:1]
    background = job.tracks[0].clips[0]
    assert isinstance(background, SolidBackground)
    background.effects.clear()
    background.color = ColorToken.PRIMARY
    snapshot = encode_render_snapshot(job, info, {})
    pool = ProcessWorkerPool(size=1, snapshot=snapshot)
    compositor = Compositor(job.tracks, info, audio={})
    try:
        await job.tracks[0].prepare(PrepareContext.from_env(info))
        await pool.start_staggered()
        pixels = []
        for frame in (84, 0, 72, 84):  # 7s, 0s, 6s, 7s at effective 12fps
            pool.submit([FrameRequest(frame_no=frame)])
            message = await pool.next_message(timeout=15)
            assert isinstance(message, FrameDone), message
            assert message.frame_no == frame
            expected = compositor.composite(TimeState(frame=frame, t=frame / 12))
            assert message.pixels == bytes(expected.toarray())
            pixels.append(message.pixels)
        assert pixels[0] != pixels[1]
        assert pixels[0] == pixels[3]
    finally:
        await pool.shutdown()
        compositor.release_worker_resources()
