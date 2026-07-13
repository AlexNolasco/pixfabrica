from typing import ClassVar

from pixfabrica_core.clips import (
    Clip,
    ClipCategory,
    ClipGL,
    ClipSkia,
    ClipTypeProtocol,
    PrepareContext,
    RenderContext,
    RenderJob,
    VisualClip,
)
from pixfabrica_core.clips.base import JobInfo, TimeState
from pixfabrica_core.clips.visual import DrawableProtocol, GLPostProcessClip


class _SampleClip(ClipSkia):
    clip_type: ClassVar[str] = "test-clips-package"


def test_clips_package_exports_clip_type_protocol() -> None:
    assert isinstance(_SampleClip, ClipTypeProtocol)


def test_clips_root_exports() -> None:
    assert Clip.__name__ == "Clip"
    assert VisualClip.__name__ == "VisualClip"
    assert ClipGL.__name__ == "ClipGL"
    assert GLPostProcessClip.__name__ == "GLPostProcessClip"
    assert RenderJob.__name__ == "RenderJob"
    assert ClipCategory.UTILITY.value == "utility"
    assert PrepareContext.__name__ == "PrepareContext"
    assert RenderContext.__name__ == "RenderContext"
    assert JobInfo.__name__ == "JobInfo"
    assert TimeState.__name__ == "TimeState"
    assert DrawableProtocol.__name__ == "DrawableProtocol"
