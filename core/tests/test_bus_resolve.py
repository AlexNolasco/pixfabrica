from pixfabrica_core.audio.bus import (
    AudioBusFrame,
    bus_timeline_for_select,
    effective_bus_name,
    resolve_bus_frame_for_select,
)


def test_effective_bus_name_defaults_to_main() -> None:
    assert effective_bus_name(None) == "main"
    assert effective_bus_name("") == "main"
    assert effective_bus_name("  ") == "main"
    assert effective_bus_name("beats") == "beats"


def test_bus_timeline_and_frame_resolve_use_main_when_unset() -> None:
    frame = AudioBusFrame.zero()
    frame.bass = 0.42
    timeline = {"main": [frame]}

    assert bus_timeline_for_select(timeline, None) == [frame]
    assert resolve_bus_frame_for_select(timeline, None, 0).bass == 0.42
