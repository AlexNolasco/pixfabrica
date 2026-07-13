from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.plugin_registry import ensure_plugins_registered
from pixfabrica_api.routes.preview_clip import (
    _clip_payload_for_deserialize,
    _fingerprint,
    _preview_audio_for_clip,
    render_error_frame,
)
from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.composition.track import FillLayout, SkiaTrack


def test_render_error_frame_size() -> None:
    raw = render_error_frame(128, 64)
    assert len(raw) == 128 * 64 * 4


def test_clip_payload_merges_catalog_defaults() -> None:
    ensure_plugins_registered()
    rebuild_catalog_cache()
    payload = _clip_payload_for_deserialize(
        {
            "clip_type": "std-static-text",
            "id": "el-1",
            "typography_role": "body_medium",
        },
        8.0,
    )
    assert payload["text"] == "{TITLE}"
    assert payload["typography_role"] == "body_medium"
    assert payload["start"] == 0.0
    assert payload["duration"] == 8.0


def test_job_info_scales_typography_like_render_job() -> None:
    from pixfabrica_api.routes.preview_clip import _job_info_from_msg

    msg = {
        "height": 720,
        "reference_height": 1080,
        "typography": {"body_medium": {"family": "Inter", "weight": 500, "size": 30.0}},
        "fps": 30,
    }
    info = _job_info_from_msg(msg, 480, 270, 8.0)
    assert info.height == 270
    assert info.design_height == 720
    assert abs(info.typography.body_medium.size - 7.5) < 0.01


def test_fingerprint_changes_with_clip() -> None:
    base = {
        "clip": {"clip_type": "std-gradient", "id": "a"},
        "track_kind": "skia",
        "fps": 30,
    }
    a = _fingerprint(base, 960, 540)
    b = _fingerprint({**base, "clip": {**base["clip"], "id": "b"}}, 960, 540)
    assert a != b


def _frame() -> AudioBusFrame:
    return AudioBusFrame(
        spectrum=[0.0] * 64,
        bass=0.5,
        mid=0.0,
        high=0.0,
        beat=False,
        amplitude=0.5,
    )


def test_preview_audio_for_clip_bus_active_blur(monkeypatch) -> None:
    ensure_plugins_registered()
    from pixfabrica_core.composition.registry import deserialize_clip

    clip = deserialize_clip(
        {
            "clip_type": "std-gradient",
            "id": "img1",
            "start": 0.0,
            "duration": 8.0,
            "enabled": True,
            "effects": [
                {
                    "effect_type": "std-blur-skia",
                    "id": "fx1",
                    "enabled": True,
                    "sensitivity": 0.5,
                    "bus_select": "drums",
                }
            ],
        }
    )
    track = SkiaTrack(
        id="t1",
        start=0.0,
        duration=8.0,
        enabled=True,
        layout=FillLayout(),
        clips=[clip],
    )

    def fake_timeline(bus: str, **kwargs) -> dict[str, list[AudioBusFrame]]:
        assert bus == "drums"
        return {bus: [_frame()]}

    monkeypatch.setattr(
        "pixfabrica_api.routes.preview_clip.preview_timeline_for_bus",
        fake_timeline,
    )
    monkeypatch.setattr(
        "pixfabrica_api.routes.preview_clip.list_preview_sample_ids",
        lambda: ["drums"],
    )

    audio = _preview_audio_for_clip(track, fps=30.0, loop_seconds=8.0, msg={})
    assert set(audio) == {"drums"}
    assert len(audio["drums"]) == 1
    assert audio["drums"][0].bass == 0.5


def test_preview_audio_for_clip_multi_bus(monkeypatch) -> None:
    ensure_plugins_registered()
    from pixfabrica_core.composition.registry import deserialize_clip

    clip = deserialize_clip(
        {
            "clip_type": "std-audio-debug",
            "id": "bg1",
            "start": 0.0,
            "duration": 8.0,
            "enabled": True,
            "bus_select": "main",
            "effects": [
                {
                    "effect_type": "std-blur-skia",
                    "id": "fx1",
                    "enabled": True,
                    "bus_select": "drums",
                    "sensitivity": 0.5,
                }
            ],
        }
    )
    track = SkiaTrack(
        id="t1",
        start=0.0,
        duration=8.0,
        enabled=True,
        layout=FillLayout(),
        clips=[clip],
    )

    def fake_timeline(bus: str, **kwargs) -> dict[str, list[AudioBusFrame]]:
        return {bus: [_frame()]}

    monkeypatch.setattr(
        "pixfabrica_api.routes.preview_clip.preview_timeline_for_bus",
        fake_timeline,
    )
    monkeypatch.setattr(
        "pixfabrica_api.routes.preview_clip.list_preview_sample_ids",
        lambda: ["drums"],
    )

    audio = _preview_audio_for_clip(track, fps=30.0, loop_seconds=8.0, msg={})
    assert set(audio) == {"drums", "main"}


def test_preview_audio_for_clip_static_blur_returns_empty(monkeypatch) -> None:
    ensure_plugins_registered()
    from pixfabrica_core.composition.registry import deserialize_clip

    clip = deserialize_clip(
        {
            "clip_type": "std-gradient",
            "id": "img1",
            "start": 0.0,
            "duration": 8.0,
            "enabled": True,
            "effects": [
                {
                    "effect_type": "std-blur-skia",
                    "id": "fx1",
                    "enabled": True,
                    "sensitivity": 0.0,
                    "bus_select": "drums",
                }
            ],
        }
    )
    track = SkiaTrack(
        id="t1",
        start=0.0,
        duration=8.0,
        enabled=True,
        layout=FillLayout(),
        clips=[clip],
    )

    def fail_timeline(*_args, **_kwargs) -> dict[str, list[AudioBusFrame]]:
        raise AssertionError("static blur should not request preview audio")

    monkeypatch.setattr(
        "pixfabrica_api.routes.preview_clip.preview_timeline_for_bus",
        fail_timeline,
    )

    assert _preview_audio_for_clip(track, fps=30.0, loop_seconds=8.0, msg={}) == {}
