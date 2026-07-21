"""Plugin icon overrides — register custom SVGs for specific clip_type values.

Import this module from pixfabrica_std.__init__ so registration runs at discovery.

Example:
    from pixfabrica_core.composition.icon_registry import StaticIconGenerator, register_icon

    register_icon("std-gltf-mesh", StaticIconGenerator("<svg>...</svg>"))
"""

from pixfabrica_core.composition.icon_registry import StaticIconGenerator, register_icon

register_icon(
    "std-ascend-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5 22 Q 4.5 18 5.5 13 Q 6 10 5 8"/>'
        '<path d="M11 22 Q 10.5 18 11.5 13 Q 12 9 11 6"/>'
        '<line x1="17" y1="22" x2="17" y2="11"/>'
        '<circle cx="17" cy="9" r="2"/>'
        "</svg>"
    ),
)

register_icon(
    "std-fractal-plasma-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="2"/>'
        '<ellipse cx="12" cy="12" rx="10" ry="3.5"/>'
        '<ellipse cx="12" cy="12" rx="10" ry="3.5" transform="rotate(60 12 12)"/>'
        '<ellipse cx="12" cy="12" rx="10" ry="3.5" transform="rotate(-60 12 12)"/>'
        "</svg>"
    ),
)

register_icon(
    "std-heart-fireworks-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M15 5v-2M15 13v2M11 9h-2M19 9h2M13 7l-1.5-1.5M17 7l1.5-1.5M13 11l-1.5 1.5M17 11l1.5 1.5"/>'
        '<path d="M6 14.5v-1.5M6 17.5v1.5M4.5 16h-1.5M7.5 16h1.5M4.5 14.5l-1-1M7.5 17.5l1 1"/>'
        '<path d="M6 3.5v-1.5M6 6.5v1.5M4.5 5h-1.5M7.5 5h1.5M4.5 6.5l-1 1M7.5 3.5l1-1"/>'
        "</svg>"
    ),
)

register_icon(
    "std-plasma-ring-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/>'
        '<circle cx="12" cy="12" r="5"/>'
        '<circle cx="12" cy="3" r="1"/>'
        "</svg>"
    ),
)

register_icon(
    "std-neon-ring-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="7" stroke-opacity="0.35"/>'
        '<circle cx="12" cy="12" r="7"/>'
        '<line x1="12" y1="5" x2="12" y2="2"/>'
        '<line x1="17" y1="7" x2="19" y2="5"/>'
        '<line x1="19" y1="12" x2="22" y2="12"/>'
        '<line x1="17" y1="17" x2="19" y2="19"/>'
        '<line x1="7" y1="7" x2="5" y2="5"/>'
        '<line x1="5" y1="12" x2="2" y2="12"/>'
        '<line x1="7" y1="17" x2="5" y2="19"/>'
        "</svg>"
    ),
)

register_icon(
    "std-hex-background-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 5l3.5 2v4l3.5 2v4l-3.5 2-3.5-2-3.5 2-3.5-2v-4l3.5-2V7z"/>'
        '<path d="M12 13v4M12 13l3.5-2M12 13l-3.5-2"/>'
        "</svg>"
    ),
)


register_icon(
    "std-warped-grid-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 8h6v6H4zM14 6h6v6h-6zM9 14h6v6H9z"/>'
        '<path d="M3 20L21 4" opacity="0.35"/>'
        "</svg>"
    ),
)

register_icon(
    "std-music-room-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="4" y="4" width="16" height="16" rx="1" opacity="0.35"/>'
        '<path d="M7 14V10M10 15V9M13 13V11M16 14V10"/>'
        '<circle cx="12" cy="12" r="2" opacity="0.25"/>'
        "</svg>"
    ),
)

register_icon(
    "std-led-eq-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="3" y1="20" x2="21" y2="20" opacity="0.35"/>'
        '<line x1="5" y1="17" x2="5" y2="14"/>'
        '<line x1="5" y1="12.5" x2="5" y2="9.5"/>'
        '<line x1="5" y1="8" x2="5" y2="5"/>'
        '<line x1="8.5" y1="17" x2="8.5" y2="13"/>'
        '<line x1="8.5" y1="11" x2="8.5" y2="7"/>'
        '<line x1="8.5" y1="5.5" x2="8.5" y2="4"/>'
        '<line x1="12" y1="17" x2="12" y2="12"/>'
        '<line x1="12" y1="10" x2="12" y2="6"/>'
        '<line x1="12" y1="4.5" x2="12" y2="3"/>'
        '<line x1="15.5" y1="17" x2="15.5" y2="11"/>'
        '<line x1="15.5" y1="9" x2="15.5" y2="5"/>'
        '<line x1="15.5" y1="4" x2="15.5" y2="3"/>'
        '<line x1="19" y1="17" x2="19" y2="14"/>'
        '<line x1="19" y1="12" x2="19" y2="8"/>'
        '<line x1="19" y1="6.5" x2="19" y2="4"/>'
        "</svg>"
    ),
)

register_icon(
    "std-inferno-tunnel-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        "<!-- Tunnel Structure -->"
        '<path d="M12 2v20M2 12h20M4.9 4.9l14.2 14.2M19.1 4.9L4.9 19.1"/>'
        "<!-- Receding Flames -->"
        '<path d="M15.5 15.5c-.5-.5-1-1.2-1.5-1.5 0 .5-.1 1-.3 1.5.3-.5.6-1 .8-1.5-.1 1-.1 2 .2 3"/>'
        '<path d="M8.5 8.5c.5.5 1 1.2 1.5 1.5 0-.5.1-1 .3-1.5-.3.5-.6 1-.8 1.5.1-1 .1-2-.2-3"/>'
        '<path d="M15.5 8.5c-.5.5-1.2 1-1.5 1.5.5 0 1-.1 1.5-.3-.5.3-1 .6-1.5.8 1 .1 2 .1 3-.2"/>'
        '<path d="M8.5 15.5c.5-.5 1.2-1 1.5-1.5-.5 0-1 .1-1.5.3.5-.3 1-.6 1.5-.8-1-.1-2-.1-3 .2"/>'
        "<!-- Central Boundary -->"
        '<circle cx="12" cy="12" r="3"/>'
        "</svg>"
    ),
)


register_icon(
    "std-cosmic-network-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<path d="M3 3l5 5M21 4l-4 3M20 21l-4-4M4 20l3-4"/>'
        ""
        '<polygon points="8,8 17,7 16,17 7,16"/>'
        '<path d="M8 8l4 4M17 7l-5 5M16 17l-4-5M7 16l5-5"/>'
        ""
        '<circle cx="12" cy="12" r="1"/>'
        '<circle cx="8" cy="8" r="1"/>'
        '<circle cx="17" cy="7" r="1"/>'
        '<circle cx="16" cy="17" r="1"/>'
        '<circle cx="7" cy="16" r="1"/>'
        ""
        '<path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>'
        "</svg>"
    ),
)

register_icon(
    "std-vu-meter",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<path d="M4 18 A 8 8 0 0 1 20 18"/>'
        ""
        '<line x1="12" y1="18" x2="9" y2="11"/>'
        ""
        '<line x1="12" y1="10" x2="12" y2="8"/>'
        '<line x1="8" y1="12" x2="6.5" y2="11"/>'
        '<line x1="16" y1="12" x2="17.5" y2="11"/>'
        "</svg>"
    ),
)

register_icon(
    "std-waveform-band",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<g transform="rotate(-15 12 12)">'
        ""
        '<rect x="3" y="7" width="18" height="10" rx="2"/>'
        ""
        '<path d="M3 12 Q 4.5 2 6 12 T 9 12 T 12 12 T 15 12 T 18 12 T 21 12"/>'
        "</g>"
        "</svg>"
    ),
)

register_icon(
    "std-mockup-eq",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<rect x="3" y="4" width="18" height="16" rx="1"/>'
        ""
        '<rect x="7" y="8" width="10" height="8" rx="0.5" stroke-dasharray="2 1"/>'
        ""
        '<path d="M8 14 V11 M10.5 14 V10 M13 14 V12 M15.5 14 V9"/>'
        "</svg>"
    ),
)

register_icon(
    "std-background-image",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<path d="M6 2H2v4M18 2h4v4M6 22H2v-4M18 22h4v-4"/>'
        ""
        '<rect x="6" y="6" width="12" height="12" rx="1"/>'
        ""
        '<circle cx="9.5" cy="9.5" r="1.5"/>'
        ""
        '<path d="M6 15l3-3 2 2 3-3 4 4"/>'
        "</svg>"
    ),
)

register_icon(
    "std-vinyl-record",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<rect x="3" y="5" width="14" height="14" rx="1"/>'
        ""
        '<circle cx="10" cy="12" r="3"/>'
        ""
        '<path d="M17 6a6 6 0 0 1 0 12"/>'
        ""
        '<path d="M17 8a4 4 0 0 1 0 8"/>'
        ""
        '<path d="M17 10.5a1.5 1.5 0 0 1 0 3"/>'
        "</svg>"
    ),
)


register_icon(
    "std-campfire-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<path d="M8 9c-2-2-1-4 0-5s0-3-1-4"/>'
        '<path d="M16 10c2-2 1-4 0-5s0-3 1-4"/>'
        ""
        '<path d="M12 4v-1.5M15.5 5.5v-1.5M8.5 4.5v-1.5"/>'
        ""
        '<path d="M12 22c3.3 0 6-2.7 6-6 0-4-6-9-6-9s-6 5-6 9c0 3.3 2.7 6 6 6z"/>'
        '<path d="M12 18c1.6 0 3-1.4 3-3 0-2-3-4.5-3-4.5s-3 2.5-3 4.5c0 1.6 1.4 3 3 3z"/>'
        "</svg>"
    ),
)


register_icon(
    "std-heart-dance-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />'
        ""
        '<path d="M16 6.5c2.3 0 4 1.7 4 4" stroke-opacity="0.5"/>'
        '<path d="M8 6.5c-2.3 0-4 1.7-4 4" stroke-opacity="0.5"/>'
        '<path d="M14 18.5l1 1" stroke-opacity="0.5"/>'
        '<path d="M10 18.5l-1 1" stroke-opacity="0.5"/>'
        "</svg>"
    ),
)


register_icon(
    "std-sun-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none"/>'
        '<path d="M12 4.5c2.2 0.4 3.8 1.6 4.6 3.4" stroke-opacity="0.75"/>'
        '<path d="M19.5 12c-0.4 2.2-1.6 3.8-3.4 4.6" stroke-opacity="0.55"/>'
        '<path d="M12 19.5c-2.2-0.4-3.8-1.6-4.6-3.4" stroke-opacity="0.75"/>'
        '<path d="M4.5 12c0.4-2.2 1.6-3.8 3.4-4.6" stroke-opacity="0.55"/>'
        "</svg>"
    ),
)

register_icon(
    "std-star-nest-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<path d="M2 2l3 3M22 2l-3 3M2 22l3-3M22 22l-3-3"/>'
        ""
        '<path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>'
        ""
        '<circle cx="17" cy="7" r="0.5"/>'
        '<circle cx="7" cy="17" r="0.5"/>'
        '<circle cx="7" cy="7" r="0.5"/>'
        '<circle cx="17" cy="17" r="0.5"/>'
        ""
        '<path d="M12 5l1.5 5.5L19 12l-5.5 1.5L12 19l-1.5-5.5L5 12l5.5-1.5z"/>'
        ""
        '<path d="M12 8l0.5 3.5L16 12l-3.5 0.5L12 16l-0.5-3.5L8 12l3.5-0.5z"/>'
        "</svg>"
    ),
)


register_icon(
    "std-scifi-widget-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        ""
        '<circle cx="12" cy="12" r="7"/>'
        '<circle cx="12" cy="12" r="3"/>'
        ""
        '<path d="M12 5V3M12 21v-2M5 12H3M21 12h-2"/>'
        '<path d="M7.05 7.05L5.64 5.64M18.36 18.36l-1.41-1.41M7.05 16.95l-1.41 1.41M18.36 5.64l-1.41 1.41"/>'
        ""
        '<rect x="16" y="16" width="5" height="2" rx="0.5" stroke-width="1.5"/>'
        "</svg>"
    ),
)


register_icon(
    "std-singularity-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 3a9 9 0 0 1 9 9" stroke-opacity="0.9"/>'
        '<path d="M12 21a9 9 0 0 1-9-9" stroke-opacity="0.9"/>'
        '<path d="M12 6.5A5.5 5.5 0 0 1 17.5 12" stroke-opacity="0.6"/>'
        '<path d="M12 17.5A5.5 5.5 0 0 1 6.5 12" stroke-opacity="0.6"/>'
        "</svg>"
    ),
)

_SPACER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
    ' fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="3 2">'
    '<rect x="5" y="5" width="14" height="14" rx="1"/>'
    "</svg>"
)

register_icon(
    "std-radial-rays-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="3"/>'
        '<line x1="12" y1="8" x2="12" y2="3"/>'
        '<line x1="14.8" y1="9.2" x2="18.4" y2="5.6"/>'
        '<line x1="16" y1="12" x2="21" y2="12"/>'
        '<line x1="14.8" y1="14.8" x2="18.4" y2="18.4"/>'
        '<line x1="12" y1="16" x2="12" y2="21"/>'
        '<line x1="9.2" y1="14.8" x2="5.6" y2="18.4"/>'
        '<line x1="8" y1="12" x2="3" y2="12"/>'
        '<line x1="9.2" y1="9.2" x2="5.6" y2="5.6"/>'
        "</svg>"
    ),
)

register_icon(
    "std-radial-bars-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/>'
        '<circle cx="12" cy="12" r="4"/>'
        '<circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/>'
        '<path d="M18 12A6 6 0 0 1 6 12"/>'
        '<path d="M12 4.5A7.5 7.5 0 1 1 4.5 12"/>'
        "</svg>"
    ),
)

register_icon(
    "std-star-pulse-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 3l1.4 4.3L18 8.5l-3.5 2.6L15.5 16 12 13.2 8.5 16l1-4.9L6 8.5l4.6-1.2z"/>'
        '<path d="M4 12h2M18 12h2M12 4v1.5M12 18.5V20" stroke-opacity="0.45"/>'
        "</svg>"
    ),
)

register_icon(
    "std-waveform-bars",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="3" y1="11" x2="3" y2="13"/>'
        '<line x1="6" y1="9" x2="6" y2="15"/>'
        '<line x1="9" y1="5" x2="9" y2="19"/>'
        '<line x1="12" y1="7" x2="12" y2="17"/>'
        '<line x1="15" y1="4" x2="15" y2="20"/>'
        '<line x1="18" y1="9" x2="18" y2="15"/>'
        '<line x1="21" y1="11" x2="21" y2="13"/>'
        "</svg>"
    ),
)

register_icon(
    "std-spectrum-bars",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="5" y1="15" x2="5" y2="20"/>'
        '<line x1="8.5" y1="8" x2="8.5" y2="20"/>'
        '<line x1="12" y1="11" x2="12" y2="20"/>'
        '<line x1="15.5" y1="6" x2="15.5" y2="20"/>'
        '<line x1="19" y1="13" x2="19" y2="20"/>'
        "</svg>"
    ),
)

register_icon(
    "std-wavy-lines-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M2 6C5 4 9 4 12 6C15 8 19 8 22 6"/>'
        '<path d="M2 12C5 10 9 10 12 12C15 14 19 14 22 12"/>'
        '<path d="M2 18C5 16 9 16 12 18C15 20 19 20 22 18"/>'
        "</svg>"
    ),
)

register_icon(
    "std-progress-bar-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="2" y1="12" x2="22" y2="12" stroke-opacity="0.35"/>'
        '<line x1="2" y1="12" x2="15" y2="12"/>'
        '<circle cx="15" cy="12" r="2" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

_PROGRESS_BAR_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
    ' fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<text x="1" y="9" font-size="5" fill="currentColor" stroke="none">0:08</text>'
    '<line x1="8" y1="12" x2="22" y2="12" stroke-opacity="0.35"/>'
    '<line x1="8" y1="12" x2="17" y2="12"/>'
    '<circle cx="17" cy="12" r="1.5" fill="currentColor" stroke="none"/>'
    '<text x="18" y="9" font-size="5" fill="currentColor" stroke="none" opacity="0.5">3:09</text>'
    "</svg>"
)

register_icon("std-progress-bar", StaticIconGenerator(_PROGRESS_BAR_SVG))

_CIRCULAR_PROGRESS_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
    ' fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="9" stroke-opacity="0.35"/>'
    '<path d="M12 3 A 9 9 0 0 1 19.2 16.5" stroke-width="2.5"/>'
    "</svg>"
)

register_icon("std-circular-progress", StaticIconGenerator(_CIRCULAR_PROGRESS_SVG))

_TIME_COUNTER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
    ' fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="13" r="8" stroke-opacity="0.35"/>'
    '<path d="M12 9v4l2.5 2.5"/>'
    '<path d="M9 3h6"/>'
    '<text x="5" y="8" font-size="5" fill="currentColor" stroke="none" font-family="monospace">0:08</text>'
    "</svg>"
)

register_icon("std-time-counter", StaticIconGenerator(_TIME_COUNTER_SVG))

_SWEEP_LINES_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
    ' fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="5" y1="20" x2="18" y2="7"/>'
    '<line x1="2" y1="17" x2="9" y2="10"/>'
    "</svg>"
)

register_icon("std-sweep-lines-gl", StaticIconGenerator(_SWEEP_LINES_SVG))
register_icon("std-sweep-lines", StaticIconGenerator(_SWEEP_LINES_SVG))

register_icon(
    "std-border-plasma-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="4" width="18" height="16" rx="1" stroke-opacity="0.35"/>'
        '<path d="M21 15L21 4L8 4"/>'
        '<circle cx="8" cy="4" r="1.5" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

register_icon(
    "std-drifting-dust-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="6" cy="8" r="0.75" fill="currentColor" stroke="none"/>'
        '<circle cx="11" cy="11" r="1" fill="currentColor" stroke="none" opacity="0.7"/>'
        '<circle cx="16" cy="9" r="0.6" fill="currentColor" stroke="none" opacity="0.5"/>'
        '<circle cx="19" cy="14" r="0.85" fill="currentColor" stroke="none" opacity="0.65"/>'
        '<path d="M4 16h14" opacity="0.25"/>'
        '<path d="M18 12l3-1M18 12l-2 2" opacity="0.6"/>'
        "</svg>"
    ),
)

register_icon(
    "std-drifting-embers-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 20c0-4 2-7 2-10a2 2 0 1 0-4 0c0 3 2 6 2 10z" opacity="0.5"/>'
        '<path d="M7 18c0-3 1.5-5 1.5-7.5a1.5 1.5 0 1 0-3 0C5.5 13 7 15 7 18z"/>'
        '<path d="M17 16c0-2.5 1.2-4.5 1.2-6.8a1.2 1.2 0 1 0-2.4 0C15.8 11.5 17 13.5 17 16z"/>'
        '<line x1="4" y1="21" x2="20" y2="21" opacity="0.35"/>'
        "</svg>"
    ),
)

register_icon(
    "std-snow-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="6" y1="4" x2="6" y2="8"/>'
        '<line x1="4.3" y1="5" x2="7.7" y2="7"/>'
        '<line x1="4.3" y1="7" x2="7.7" y2="5"/>'
        '<line x1="18" y1="10" x2="18" y2="14"/>'
        '<line x1="16.3" y1="11" x2="19.7" y2="13"/>'
        '<line x1="16.3" y1="13" x2="19.7" y2="11"/>'
        '<line x1="10" y1="17" x2="10" y2="21"/>'
        '<line x1="8.3" y1="18" x2="11.7" y2="20"/>'
        '<line x1="8.3" y1="20" x2="11.7" y2="18"/>'
        "</svg>"
    ),
)

register_icon(
    "std-edge-smoke-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 20c2-3 3-6 3-9"/>'
        '<path d="M8 20c1.5-2.5 2.5-5.5 2.5-9"/>'
        '<path d="M13 20c1-2 2-5 2-8"/>'
        '<path d="M18 20c0.8-1.8 1.5-4 1.5-7"/>'
        '<path d="M4 11c2-1 4-1.5 6-1"/>'
        '<path d="M12 9c2-0.8 4-0.5 6 0.5"/>'
        "</svg>"
    ),
)

register_icon(
    "std-dying-universe-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="2" y1="21" x2="22" y2="21"/>'
        '<circle cx="5" cy="7" r="2.5"/>'
        '<circle cx="12" cy="14" r="2.5"/>'
        '<ellipse cx="19" cy="19.5" rx="3.5" ry="1.5"/>'
        "</svg>"
    ),
)

register_icon(
    "std-orbit-trail-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 12C15 6 22 6 22 12C22 18 15 18 12 12C9 6 2 6 2 12C2 18 9 18 12 12"/>'
        "</svg>"
    ),
)

register_icon(
    "std-animated-gradient-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="16" r="5"/>'
        '<circle cx="8" cy="9" r="3"/>'
        '<circle cx="17" cy="4" r="2"/>'
        "</svg>"
    ),
)

register_icon(
    "std-sepia-nebula-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        # Spiral nebula arms swirling into a bright core
        '<path d="M12 12c0-3 2.5-5.5 5.5-5.5"/>'
        '<path d="M12 12c0 3-2.5 5.5-5.5 5.5" stroke-opacity="0.8"/>'
        '<path d="M12 12c3 0 5.5 2.5 5.5 5.5" stroke-opacity="0.55"/>'
        '<path d="M12 12c-3 0-5.5-2.5-5.5-5.5" stroke-opacity="0.55"/>'
        # Glowing core + a few scattered stars
        '<circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/>'
        '<circle cx="4" cy="5" r="0.6" fill="currentColor" stroke="none"/>'
        '<circle cx="20" cy="19" r="0.6" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

register_icon(
    "std-liquid-metal-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        # Molten droplet / blob of liquid metal
        '<path d="M12 3c2.5 3 6 5.5 6 9.5a6 6 0 0 1-12 0C6 8.5 9.5 6 12 3z"/>'
        # Flowing veins inside the blob
        '<path d="M9 13c1.5-1.5 4.5-1.5 6 0" stroke-opacity="0.6"/>'
        '<path d="M9.5 16.5c1.2-1 3.8-1 5 0" stroke-opacity="0.45"/>'
        # Specular highlight
        '<circle cx="10" cy="10" r="0.9" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

register_icon(
    "std-neon-sunset-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="7" r="3" fill="currentColor" stroke="none"/>'
        '<path d="M4 20h16"/>'
        '<path d="M6 20l3-6M18 20l-3-6"/>'
        '<path d="M9 14h6" stroke-opacity="0.5"/>'
        "</svg>"
    ),
)

register_icon(
    "std-neon-tunnel-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="2" y1="22" x2="12" y2="8"/>'
        '<line x1="22" y1="22" x2="12" y2="8"/>'
        '<circle cx="12" cy="8" r="2"/>'
        "</svg>"
    ),
)

register_icon(
    "std-fuzzy-clouds-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 6Q7 3 10 6Q13 3 16 6Q19 3 21 6"/>'
        '<circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>'
        '<path d="M3 18Q7 21 10 18Q13 21 16 18Q19 21 21 18"/>'
        "</svg>"
    ),
)

register_icon(
    "std-fire-base-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8 22C5 18 8 13 12 10C16 13 19 18 16 22Z"/>'
        '<path d="M10 22C9 20 10 18 12 16C14 18 15 20 14 22Z"/>'
        "</svg>"
    ),
)

register_icon(
    "std-cloud",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>'
        "</svg>"
    ),
)

register_icon(
    "std-video",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="2" y="4" width="20" height="16" rx="2"/>'
        '<path d="M10 9l6 3-6 3z" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

register_icon(
    "std-image",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="4" width="18" height="16" rx="1"/>'
        '<circle cx="8.5" cy="9.5" r="1.5"/>'
        '<path d="M3 15l4-4 4 3 3-4 7 5"/>'
        "</svg>"
    ),
)

register_icon(
    "std-hyperspace-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 3v18"/>'
        '<path d="M8 7l4-4 4 4"/>'
        '<path d="M6 11h2M16 11h2M7 15h1.5M15.5 15H17"/>'
        '<path d="M9 19l1.5-2M15 19l-1.5-2" stroke-opacity="0.55"/>'
        '<circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

register_icon(
    "std-star-dust-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="5" cy="12" r="0.6" fill="currentColor" stroke="none"/>'
        '<circle cx="9" cy="7" r="0.8" fill="currentColor" stroke="none" opacity="0.8"/>'
        '<circle cx="14" cy="15" r="0.6" fill="currentColor" stroke="none" opacity="0.6"/>'
        '<circle cx="19" cy="9" r="0.7" fill="currentColor" stroke="none" opacity="0.75"/>'
        '<circle cx="11" cy="18" r="0.5" fill="currentColor" stroke="none" opacity="0.5"/>'
        '<circle cx="17" cy="5" r="0.55" fill="currentColor" stroke="none" opacity="0.65"/>'
        '<path d="M3 12l3-0.5" stroke-opacity="0.4"/>'
        '<path d="M7 7l3-0.5" stroke-opacity="0.4"/>'
        '<path d="M12 15l3-0.5" stroke-opacity="0.4"/>'
        '<path d="M17 9l3-0.5" stroke-opacity="0.4"/>'
        "</svg>"
    ),
)

register_icon("std-spacer-skia", StaticIconGenerator(_SPACER_SVG))
register_icon("std-spacer-gl", StaticIconGenerator(_SPACER_SVG))

register_icon(
    "std-fade-gradient-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<rect x="3" y="3" width="18" height="18" rx="2" stroke-opacity="0.35"/>'
        '<defs><linearGradient id="fg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="currentColor" stop-opacity="0.9"/>'
        '<stop offset="100%" stop-color="currentColor" stop-opacity="0"/>'
        "</linearGradient></defs>"
        '<rect x="3" y="3" width="18" height="18" rx="2" fill="url(#fg)"/>'
        "</svg>"
    ),
)

register_icon(
    "std-track-card",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="5" width="18" height="14" rx="2"/>'
        '<rect x="3" y="5" width="18" height="2.5" rx="1" fill="currentColor" stroke="none"/>'
        '<rect x="5.5" y="9.5" width="5" height="5" rx="0.75"/>'
        '<line x1="12.5" y1="10.5" x2="17" y2="10.5"/>'
        '<line x1="12.5" y1="13.5" x2="15.5" y2="13.5"/>'
        '<circle cx="18.5" cy="12" r="2.25"/>'
        '<path d="M17.6 11.2v1.6l1.4-.8-1.4-.8z" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

register_icon(
    "std-mini-track-card",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="4" y="14" width="16" height="7" rx="1.5"/>'
        '<rect x="5.5" y="15.5" width="4" height="4" rx="0.5"/>'
        '<line x1="11" y1="16.5" x2="17" y2="16.5"/>'
        '<line x1="11" y1="18.5" x2="15" y2="18.5"/>'
        "</svg>"
    ),
)

register_icon(
    "std-eq-bars-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="currentColor" stroke="none">'
        '<rect x="3" y="14" width="1.6" height="4"/>'
        '<rect x="5.5" y="11" width="1.6" height="7"/>'
        '<rect x="8" y="13" width="1.6" height="5"/>'
        '<rect x="10.5" y="9" width="1.6" height="9"/>'
        '<rect x="13" y="12" width="1.6" height="6"/>'
        '<rect x="15.5" y="10" width="1.6" height="8"/>'
        '<rect x="18" y="13.5" width="1.6" height="4.5"/>'
        '<rect x="20.5" y="11.5" width="1.6" height="6.5"/>'
        "</svg>"
    ),
)

register_icon(
    "std-turbulent-ring-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="1.6"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="12" rx="8" ry="3.5"/>'
        '<ellipse cx="12" cy="12" rx="5" ry="2" opacity="0.55"/>'
        '<path d="M4 12c1.5-1 3-1.5 4-1" opacity="0.7"/>'
        '<path d="M16 13c1 .3 2.5.8 4 1.2" opacity="0.7"/>'
        "</svg>"
    ),
)

register_icon(
    "std-eq-wave-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="currentColor" stroke="none">'
        '<path d="M3 18c2.2-3.2 3.8 2.4 6-.8s3.8 2.8 6-.4 3.8-2.8 6-.4V18H3z"/>'
        "</svg>"
    ),
)

register_icon(
    "std-waveform-raymarch-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="2" y1="12" x2="22" y2="12" stroke-opacity="0.3"/>'
        '<path d="M2 9c2-2 3 2 5 0s3-2 5 0 3 2 5 0 3-2 5 0"/>'
        '<path d="M2 15c2 2 3-2 5 0s3 2 5 0 3-2 5 0 3 2 5 0" stroke-opacity="0.5"/>'
        "</svg>"
    ),
)

register_icon(
    "std-eq-led-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="currentColor" stroke="none">'
        '<circle cx="4.5" cy="17" r="1.1"/>'
        '<circle cx="4.5" cy="14.5" r="1.1"/>'
        '<circle cx="4.5" cy="12" r="1.1"/>'
        '<circle cx="8" cy="16" r="1.1"/>'
        '<circle cx="8" cy="13" r="1.1"/>'
        '<circle cx="8" cy="10.5" r="1.1"/>'
        '<circle cx="11.5" cy="15" r="1.1"/>'
        '<circle cx="11.5" cy="11.5" r="1.1"/>'
        '<circle cx="11.5" cy="8.5" r="1.1"/>'
        '<circle cx="15" cy="16.5" r="1.1"/>'
        '<circle cx="15" cy="13" r="1.1"/>'
        '<circle cx="15" cy="10" r="1.1"/>'
        '<circle cx="18.5" cy="15.5" r="1.1"/>'
        '<circle cx="18.5" cy="12.5" r="1.1"/>'
        '<circle cx="18.5" cy="10" r="1.1"/>'
        "</svg>"
    ),
)

register_icon(
    "std-capsule-bars-gl",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="4" y1="12" x2="4" y2="12"/>'
        '<path d="M4 15.5V8.5a1.5 1.5 0 0 1 3 0v7a1.5 1.5 0 0 1-3 0z"/>'
        '<path d="M8.5 14.5V9.5a2 2 0 0 1 4 0v5a2 2 0 0 1-4 0z"/>'
        '<path d="M13 16V8a2.5 2.5 0 0 1 5 0v8a2.5 2.5 0 0 1-5 0z"/>'
        '<path d="M18.5 14.5V9.5a2 2 0 0 1 4 0v5a2 2 0 0 1-4 0z"/>'
        "</svg>"
    ),
)

register_icon(
    "std-lyrics-caption",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="2" y="6" width="13" height="12" rx="2"/>'
        '<line x1="5" y1="10.5" x2="12" y2="10.5"/>'
        '<line x1="5" y1="14" x2="10" y2="14"/>'
        '<path d="M19 16V7l3 1v9"/>'
        '<circle cx="18" cy="16.5" r="1.6" fill="currentColor" stroke="none"/>'
        '<circle cx="21" cy="17.5" r="1.6" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)

register_icon(
    "std-lyrics-pop",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="3" y1="19" x2="8" y2="19"/>'
        '<line x1="16" y1="19" x2="21" y2="19"/>'
        '<path d="M9 19c0-3.5 1.8-6 3-6s3 2.5 3 6"/>'
        '<circle cx="12" cy="11.5" r="1.7" fill="currentColor" stroke="none"/>'
        '<path d="M12 9V4.5" stroke-opacity="0.6"/>'
        '<path d="M9.5 6l1-1.5M14.5 6l-1-1.5" stroke-opacity="0.45"/>'
        "</svg>"
    ),
)

register_icon(
    "std-teleprompter-caption",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="5" width="18" height="12" rx="2"/>'
        '<line x1="6" y1="9" x2="18" y2="9"/>'
        '<line x1="6" y1="12" x2="15" y2="12" stroke-opacity="0.6"/>'
        '<path d="M8 20l4-3 4 3"/>'
        "</svg>"
    ),
)

register_icon(
    "std-word-cloud",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="none">'
        '<text x="2" y="11" font-size="10" font-family="sans-serif" fill="currentColor">A</text>'
        '<text x="13" y="8" font-size="5" font-family="sans-serif" fill="currentColor" opacity="0.7">b</text>'
        '<text x="10" y="19" font-size="7" font-family="sans-serif" fill="currentColor" opacity="0.85">C</text>'
        '<text x="17.5" y="17" font-size="4.5" font-family="sans-serif" fill="currentColor" opacity="0.6">d</text>'
        "</svg>"
    ),
)

register_icon(
    "std-info-track-card",
    StaticIconGenerator(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="5" width="18" height="15" rx="0"/>'
        '<line x1="6" y1="8.5" x2="13" y2="8.5"/>'
        '<line x1="6" y1="11" x2="11" y2="11"/>'
        '<line x1="6" y1="14" x2="14" y2="14"/>'
        '<circle cx="6.8" cy="17.2" r="0.8" fill="currentColor" stroke="none"/>'
        '<line x1="8.5" y1="17.2" x2="11.5" y2="17.2"/>'
        '<circle cx="13.5" cy="17.2" r="0.8" fill="currentColor" stroke="none"/>'
        '<line x1="15.2" y1="17.2" x2="17.5" y2="17.2"/>'
        '<path d="M18.5 8.5v5.5l2-1.2-2-1.2z" fill="currentColor" stroke="none"/>'
        "</svg>"
    ),
)
