from __future__ import annotations

import re

from pixfabrica_core.clips.base import ClipCategory

_ATTRS = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'


def _svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {_ATTRS}>{body}</svg>'


def _from_lucide(svg: str) -> str:
    """Accept a full SVG string copied from lucide.dev and normalise it."""
    inner = re.sub(r"<svg[^>]*>", "", svg).replace("</svg>", "").strip()
    return _svg(inner)


FALLBACK_ICON = _from_lucide(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
    ' stroke-linejoin="round">'
    '<rect width="18" height="18" x="3" y="3" rx="2"/>'
    '<path d="M9 9h6v6H9z"/>'
    "</svg>"
)

CATEGORY_ICONS: dict[ClipCategory, str] = {
    ClipCategory.BACKGROUND: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round" class="lucide lucide-wallpaper">'
        '<path d="M12 17v4"/><path d="M8 21h8"/>'
        '<path d="m9 17 6.1-6.1a2 2 0 0 1 2.81.01L22 15"/>'
        '<circle cx="8" cy="9" r="2"/>'
        '<rect x="2" y="3" width="20" height="14" rx="2"/>'
        "</svg>"
    ),
    ClipCategory.TEXT: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" >'
        '<path d="m15 16 2.536-7.328a1.02 1.02 1 0 1 1.928 0L22 16"/>'
        '<path d="M15.697 14h5.606"/>'
        '<path d="m2 16 4.039-9.69a.5.5 0 0 1 .923 0L11 16"/>'
        '<path d="M3.304 13h6.392"/>'
        "</svg>"
    ),
    ClipCategory.EFFECTS: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.PARTICLES: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.IMAGE: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round" class="lucide lucide-image">'
        '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>'
        '<circle cx="9" cy="9" r="2"/>'
        '<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'
        "</svg>"
    ),
    ClipCategory.MESH: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
        '<polyline points="3.27 6.96 12 12.01 20.73 6.96"/>'
        '<line x1="12" y1="22.08" x2="12" y2="12"/>'
        "</svg>"
    ),
    ClipCategory.VIDEO: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.AUDIO: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.UTILITY: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round" class="lucide lucide-wrench">'
        '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94'
        'l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>'
        "</svg>"
    ),
    ClipCategory.TRACK: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.THEME_GENERATOR: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.MATH: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.LOGIC: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.PROGRESS: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.LYRICS: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" width="168" height="168" viewBox="0 0 24 24">'
        '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/>'
        '<path d="M20 2v4"/>'
        '<path d="M22 4h-4"/>'
        '<circle cx="4" cy="20" r="2"/>'
        "</svg>"
    ),
    ClipCategory.POSTPROCESS: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<path d="M2 3L2 21M2 3L12 3M2 12L9 12"/>'
        '<path d="M14 9L22 20M22 9L14 20"/>'
        "</svg>"
    ),
    ClipCategory.PLAYER: _from_lucide(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round">'
        '<rect x="3" y="6" width="14" height="12" rx="2"/>'
        '<path d="M10 9.5v5l4-2.5-4-2.5z"/>'
        '<line x1="19" y1="9" x2="19" y2="15"/>'
        "</svg>"
    ),
}
