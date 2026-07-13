"""Preview reprepare scope and tiered graph hashing."""

from __future__ import annotations

from pixfabrica_core.preview_invalidation import (
    ReprepareScope,
    preview_audio_prepare_hash,
    resolve_reprepare_scope,
)


def test_preview_audio_hash_includes_bus_wiring() -> None:
    base = {
        "fps": 30.0,
        "duration": 10.0,
        "sounds": [{"id": "s1", "bus": "main", "source": "/a.wav", "analyzer": "fast"}],
        "tracks": [
            {
                "id": "t1",
                "enabled": True,
                "clips": [
                    {
                        "id": "e1",
                        "enabled": True,
                        "bus_select": "main",
                        "clip_type": "std-audio-debug",
                    }
                ],
            }
        ],
    }
    h0 = preview_audio_prepare_hash(base)
    unwired = {
        **base,
        "tracks": [
            {
                **base["tracks"][0],
                "clips": [{**base["tracks"][0]["clips"][0], "bus_select": ""}],
            }
        ],
    }
    assert preview_audio_prepare_hash(unwired) != h0


def test_preview_audio_hash_includes_effect_bus_wiring() -> None:
    base = {
        "fps": 30.0,
        "duration": 10.0,
        "sounds": [{"id": "s1", "bus": "drums", "source": "/a.wav", "analyzer": "fast"}],
        "tracks": [
            {
                "id": "t1",
                "enabled": True,
                "clips": [
                    {
                        "id": "e1",
                        "enabled": True,
                        "clip_type": "std-image",
                        "effects": [
                            {
                                "id": "fx1",
                                "enabled": True,
                                "effect_type": "std-blur-skia",
                                "bus_select": "drums",
                                "sensitivity": 0.5,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    h0 = preview_audio_prepare_hash(base)
    unwired = {
        **base,
        "tracks": [
            {
                **base["tracks"][0],
                "clips": [
                    {
                        **base["tracks"][0]["clips"][0],
                        "effects": [
                            {
                                **base["tracks"][0]["clips"][0]["effects"][0],
                                "sensitivity": 0.0,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    assert preview_audio_prepare_hash(unwired) != h0


def test_resolve_gl_context_only_after_clip_preview() -> None:
    scope = resolve_reprepare_scope(
        graph_changed=False,
        force_reprepare=True,
        audio_hash_changed=False,
        uses_gl=True,
    )
    assert scope == ReprepareScope.GL_CONTEXT_ONLY


def test_resolve_skip_audio_on_visual_edit() -> None:
    scope = resolve_reprepare_scope(
        graph_changed=True,
        force_reprepare=False,
        audio_hash_changed=False,
        uses_gl=True,
    )
    assert scope == ReprepareScope.SKIP_AUDIO


def test_resolve_full_when_audio_changes() -> None:
    scope = resolve_reprepare_scope(
        graph_changed=True,
        force_reprepare=False,
        audio_hash_changed=True,
        uses_gl=False,
    )
    assert scope == ReprepareScope.FULL
