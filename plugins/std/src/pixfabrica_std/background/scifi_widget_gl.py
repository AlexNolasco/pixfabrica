"""Sci-Fi Widget — single SDF HUD widget on a transparent GL layer.

## Adding widget kinds

1. Add the SDF function in ``_FRAG`` below (port from Shadertoy; use ``u_anim_t`` for time).
2. Add ``#define ELEM_*`` constant and a branch in ``widget_distance()``.
3. Append the wire value to ``SciFiWidgetKind`` and ``_WIDGET_KIND_IDS``.
4. Measure the visual center and add ``_WIDGET_ANCHOR_OFFSET`` (UV-space centroid).
5. Run ``uv run pixfabrica plugin gen-ui plugins/std`` and ``uv run pixfabrica plugin gen-nls plugins/std``.
6. Strip hardcoded UV offsets from the original — positioning uses ``offset_x`` / ``offset_y``.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import (
    ClipCategory,
    ClipGL,
    ClipPreset,
    ClipTag,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

SciFiWidgetKind = Literal[
    "wave",
    "circle_dial",
    "small_circle",
    "small_circle_2",
    "barcode",
    "slider",
    "graph",
    "scifi_panel",
    "scifi_dial",
]

_WIDGET_KIND_IDS: dict[SciFiWidgetKind, int] = {
    "wave": 0,
    "circle_dial": 1,
    "small_circle": 2,
    "small_circle_2": 3,
    "barcode": 4,
    "slider": 5,
    "graph": 6,
    "scifi_panel": 7,
    "scifi_dial": 8,
}

# UV-space visual centroid at scale=1.0; applied in the shader so offset_x/y anchor the
# drawn widget center (not the SDF math origin).
_WIDGET_ANCHOR_OFFSET: dict[SciFiWidgetKind, tuple[float, float]] = {
    "wave": (0.0, 0.0),
    "circle_dial": (-0.03, -0.01),
    "small_circle": (-0.01, 0.0),
    "small_circle_2": (-0.01, 0.0),
    "barcode": (0.0, 0.0),
    "slider": (0.0, 0.0),
    "graph": (-0.05, 0.0),
    "scifi_panel": (0.06, -0.03),
    "scifi_dial": (0.0, 0.0),
}

# UV-space hit radius at scale=1.0.
_WIDGET_HIT_RADIUS: dict[SciFiWidgetKind, float] = {
    "wave": 0.62,
    "circle_dial": 0.60,
    "small_circle": 0.34,
    "small_circle_2": 0.20,
    "barcode": 0.24,
    "slider": 0.30,
    "graph": 0.30,
    "scifi_panel": 0.48,
    "scifi_dial": 0.18,
}

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""


_ID_TO_WIDGET_KIND: dict[int, SciFiWidgetKind] = {v: k for k, v in _WIDGET_KIND_IDS.items()}


def _frag_for_widget_kind(elem_id: int) -> str:
    elem = _ID_TO_WIDGET_KIND[elem_id]
    ax, ay = _WIDGET_ANCHOR_OFFSET[elem]
    header = (
        f"#version 330 core\n"
        f"#define ELEM_ID {elem_id}\n"
        f"#define ELEM_ANCHOR vec2({ax:.4f}, {ay:.4f})"
    )
    return _FRAG.replace("#version 330 core", header, 1)


_FRAG = """
#version 330 core

#ifndef ELEM_ID
#define ELEM_ID -1
#endif

#ifndef ELEM_ANCHOR
#define ELEM_ANCHOR vec2(0.0, 0.0)
#endif

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_anim_t;
uniform float u_bound_r;

uniform vec3  u_color;
uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_scale;
uniform float u_angle;
uniform float u_brightness;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

#define ELEM_WAVE          0
#define ELEM_CIRCLE_DIAL   1
#define ELEM_SMALL_CIRCLE  2
#define ELEM_SMALL_CIRCLE2 3
#define ELEM_BARCODE       4
#define ELEM_SLIDER        5
#define ELEM_GRAPH         6
#define ELEM_SCIFI_PANEL   7
#define ELEM_SCIFI_DIAL    8

#define Rot(a) mat2(cos(a), -sin(a), sin(a), cos(a))

float S(float d, float b, float aa) {
    return smoothstep(aa, b, d);
}

float B(vec2 p, vec2 s) {
    return max(abs(p.x) - s.x, abs(p.y) - s.y);
}

#if ELEM_ID == 1 || ELEM_ID == 7
float Tri(vec2 p, vec2 s, float a) {
    return max(
        -dot(p, vec2(cos(-a), sin(-a))),
        max(dot(p, vec2(cos(a), sin(a))), max(abs(p.x) - s.x, abs(p.y) - s.y))
    );
}
#endif

#if ELEM_ID == 1 || ELEM_ID == 2 || ELEM_ID == 3
vec2 DF(vec2 a, float b) {
    float t = mod(
        atan(a.y, a.x) + 6.28 / (b * 8.0),
        6.28 / ((b * 8.0) * 0.5)
    ) + (b - 1.0) * 6.28 / (b * 8.0);
    return length(a) * cos(vec2(t) + vec2(0.0, 11.0));
}
#endif

#if ELEM_ID == 4 || ELEM_ID == 6 || ELEM_ID == 7
float Hash21(vec2 p) {
    p = fract(p * vec2(234.56, 789.34));
    p += dot(p, p + 34.56);
    return fract(p.x + p.y);
}
#endif

#if ELEM_ID == 0
float elem_main_wave(vec2 p) {
    p *= 1.5;
    float thickness = 0.003;
    vec2 prevP = p;
    float t = fract(sin(u_anim_t * 100.0)) * 0.5;

    p.x += u_anim_t * 1.0;
    p.y += sin(p.x * 8.0) * (0.05 + abs(sin(t * 10.0) * 0.12));
    float d = abs(p.y) - thickness;

    p = prevP;
    p.x -= u_anim_t * 0.5;
    p.y += sin(p.x * 3.0) * (0.1 + abs(sin(t * 9.0) * 0.13));
    float d2 = abs(p.y) - thickness;
    d = min(d, d2);

    p = prevP;
    p.x += u_anim_t * 0.7;
    p.y += sin(p.x * 5.0) * (0.1 + abs(sin(t * 9.3) * 0.15));
    d2 = abs(p.y) - thickness;
    d = min(d, d2);

    p = prevP;
    p.x -= u_anim_t * 0.6;
    p.y += sin(p.x * 10.0) * (0.1 + abs(sin(t * 9.5) * 0.08));
    d2 = abs(p.y) - thickness;
    d = min(d, d2);

    p = prevP;
    p.x += u_anim_t * 1.2;
    p.y += cos(-p.x * 15.0) * (0.1 + abs(sin(t * 10.0) * 0.1));
    d2 = abs(p.y) - thickness;
    d = min(d, d2);

    return d;
}
#endif

#if ELEM_ID == 1
float elem_circle_dial(vec2 p) {
    vec2 prevP = p;
    float st = u_anim_t * 3.0;
    mat2 animRot = Rot(radians(st) * 30.0);
    p *= animRot;

    p = DF(p, 32.0);
    p -= vec2(0.28);
    float d = B(p * Rot(radians(45.0)), vec2(0.002, 0.02));

    p = prevP;
    p *= animRot;
    float a = radians(130.0);
    d = max(dot(p, vec2(cos(a), sin(a))), d);
    a = radians(-130.0);
    d = max(dot(p, vec2(cos(a), sin(a))), d);

    p = prevP;
    animRot = Rot(radians(u_anim_t) * 20.0);
    p *= animRot;
    p = DF(p, 24.0);
    p -= vec2(0.19);
    float d2 = B(p * Rot(radians(45.0)), vec2(0.003, 0.015));

    p = prevP;
    p *= animRot;
    a = radians(137.5);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-137.5);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    d = min(d, d2);

    p = prevP;
    animRot = Rot(-radians(st) * 25.0);
    p *= animRot;
    p = DF(p, 16.0);
    p -= vec2(0.16);
    d2 = B(p * Rot(radians(45.0)), vec2(0.003, 0.01));

    p = prevP;
    p *= animRot;
    a = radians(25.5);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-25.5);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    d = min(d, d2);

    p = prevP;
    animRot = Rot(radians(st) * 35.0);
    p *= animRot;
    p = DF(p, 8.0);
    p -= vec2(0.23);
    d2 = B(p * Rot(radians(45.0)), vec2(0.02, 0.02));

    p = prevP;
    p *= animRot;
    a = radians(40.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-40.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    d = min(d, d2);

    p = prevP;
    animRot = Rot(radians(st) * 15.0);
    p *= animRot;
    d2 = abs(length(p) - 0.36) - 0.002;
    d2 = max(abs(p.x) - 0.2, d2);
    d = min(d, d2);

    p = prevP;
    animRot = Rot(radians(90.0) + radians(st) * 38.0);
    p *= animRot;
    d2 = abs(length(p) - 0.245) - 0.002;
    d2 = max(abs(p.x) - 0.1, d2);
    d = min(d, d2);

    p = prevP;
    d2 = abs(length(p) - 0.18) - 0.001;
    d = min(d, d2);

    p = prevP;
    animRot = Rot(radians(145.0) + radians(st) * 32.0);
    p *= animRot;
    d2 = abs(length(p) - 0.18) - 0.008;
    a = radians(30.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-30.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    d = min(d, d2);

    p = prevP;
    a = radians(st) * 30.0;
    p.x += cos(a) * 0.45;
    p.y += sin(a) * 0.45;
    d2 = Tri(p * Rot(-a) * Rot(radians(90.0)), vec2(0.02), radians(45.0));
    d = min(d, d2);

    p = prevP;
    a = radians(-sin(st * 0.5)) * 120.0;
    a += radians(-70.0);
    p.x += cos(a) * 0.45;
    p.y += sin(a) * 0.45;
    d2 = abs(Tri(p * Rot(-a) * Rot(radians(90.0)), vec2(0.02), radians(45.0))) - 0.001;
    d = min(d, d2);

    p = prevP;
    animRot = Rot(-radians(st) * 27.0);
    p *= animRot;
    d2 = abs(length(p) - 0.43) - 0.0001;
    d2 = max(abs(p.x) - 0.3, d2);
    d = min(d, d2);

    p = prevP;
    animRot = Rot(-radians(st) * 12.0);
    p *= animRot;
    p = DF(p, 8.0);
    p -= vec2(0.103);
    d2 = B(p * Rot(radians(45.0)), vec2(0.001, 0.007));
    d = min(d, d2);

    p = prevP;
    animRot = Rot(radians(16.8) - radians(st) * 12.0);
    p *= animRot;
    p = DF(p, 8.0);
    p -= vec2(0.098);
    d2 = B(p * Rot(radians(45.0)), vec2(0.001, 0.013));
    d = min(d, d2);

    p = prevP;
    animRot = Rot(radians(st) * 30.0);
    p *= animRot;
    p = DF(p, 10.0);
    p -= vec2(0.28);
    d2 = abs(B(p * Rot(radians(45.0)), vec2(0.02, 0.02))) - 0.001;

    p = prevP;
    p *= animRot;
    a = radians(50.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-50.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    d = min(d, d2);

    return d;
}
#endif

#if ELEM_ID == 2
float elem_small_circle(vec2 p) {
    p *= 1.3;
    vec2 prevP = p;
    float speed = 3.0;

    mat2 animRot = Rot(radians(u_anim_t * speed) * 35.0);
    p *= animRot;
    float d = abs(length(p) - 0.2) - 0.005;

    float a = radians(50.0);
    d = max(dot(p, vec2(cos(a), sin(a))), d);
    a = radians(-50.0);
    d = max(dot(p, vec2(cos(a), sin(a))), d);

    p *= Rot(radians(10.0));
    float d2 = abs(length(p) - 0.19) - 0.006;
    a = radians(60.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-60.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    d = min(d, d2);

    p = prevP;
    d2 = abs(length(p) - 0.195) - 0.0001;
    d = min(d, d2);

    p = prevP;
    animRot = Rot(-radians(u_anim_t * speed) * 30.0);
    p *= animRot;
    p = DF(p, 12.0);
    p -= vec2(0.11);
    d2 = B(p * Rot(radians(45.0)), vec2(0.003, 0.015));
    d = min(d, d2);

    p = prevP;
    animRot = Rot(radians(u_anim_t * speed) * 23.0);
    p *= animRot;
    p = DF(p, 2.5);
    p -= vec2(0.05);
    d2 = B(p * Rot(radians(45.0)), vec2(0.01));
    d = min(d, d2);

    p = prevP;
    animRot = Rot(-radians(u_anim_t * speed) * 26.0);
    p *= animRot;
    d2 = abs(length(p) - 0.11) - 0.005;
    d2 = max(abs(p.x) - 0.05, d2);
    d = min(d, d2);

    return d;
}
#endif

#if ELEM_ID == 3
float elem_small_circle2(vec2 p) {
    vec2 prevP = p;
    float speed = 3.0;
    mat2 animRot = Rot(radians(u_anim_t * speed) * 28.0);
    p *= animRot;

    float d = abs(length(p) - 0.028) - 0.0005;
    d = max(B(p, vec2(0.015, 0.1)), d);

    p = prevP;
    animRot = Rot(-radians(u_anim_t * speed) * 31.0);
    p *= animRot;
    float d2 = abs(length(p) - 0.027) - 0.004;
    float a = radians(50.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-50.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    d = min(max(-d2, d), abs(d2) - 0.001);

    p = prevP;
    animRot = Rot(-radians(u_anim_t * speed) * 30.0);
    p *= animRot;
    p = DF(p, 2.0);
    p -= vec2(0.008);
    d2 = B(p * Rot(radians(45.0)), vec2(0.0005, 0.002));
    d = min(d, d2);

    return d;
}
#endif

#if ELEM_ID == 4
float elem_barcode(vec2 p) {
    p *= 1.1;
    vec2 prevP = p;
    p.x += u_anim_t * 0.5;
    p *= 15.0;
    vec2 id = floor(p);
    float n = Hash21(vec2(id.x)) * 5.0;

    p.x = mod(p.x, 0.2) - 0.1;
    float d = abs(p.x) - ((0.01 * n) + 0.01);

    p = prevP;
    d = max(abs(p.x) - 0.15, d);
    d = max(abs(p.y) - 0.1, d);

    float d2 = abs(B(p, vec2(0.16, 0.11))) - 0.001;
    d2 = max(-(abs(p.x) - 0.14), d2);
    d2 = max(-(abs(p.y) - 0.09), d2);

    return min(d, d2);
}
#endif

#if ELEM_ID == 5
float elem_scifi_ui(vec2 p) {
    p *= 1.1;
    vec2 prevP = p;
    float d = B(p, vec2(0.15, 0.06));
    float a = radians(45.0);
    p.x = abs(p.x) - 0.195;
    p.y = abs(p.y);
    float m = dot(p, vec2(cos(a), sin(a)));
    d = max(m, d);

    p = prevP;
    p.x += 0.16;
    p.y += 0.008;
    float d2 = B(p, vec2(0.06, 0.052));
    a = radians(45.0);
    p.x = abs(p.x) - 0.095;
    p.y = abs(p.y);
    m = dot(p, vec2(cos(a), sin(a)));
    d2 = max(m, d2);

    p = prevP;
    d2 = min(d, d2);
    d2 = max(-B(p - vec2(-0.03, -0.05), vec2(0.2, 0.05)), abs(d2) - 0.003);

    return abs(d2) - 0.001;
}
#endif

#if ELEM_ID == 7
float elem_tri_animation(vec2 p) {
    vec2 prevP = p;
    p.x += u_anim_t * 0.1;
    p.x = mod(p.x, 0.04) - 0.02;
    p.x += 0.01;
    float d = abs(Tri(p * Rot(radians(-90.0)), vec2(0.012), radians(45.0))) - 0.0001;
    p = prevP;
    return max(abs(p.x) - 0.125, d);
}
#endif

#if ELEM_ID == 7
float elem_random_dot_line(vec2 p) {
    vec2 prevP = p;
    p.x += u_anim_t * 0.08;
    vec2 gv = fract(p * 17.0) - 0.5;
    vec2 id = floor(p * 17.0);
    float n = Hash21(id);
    float d = B(gv, vec2(0.25 * (n * 2.0), 0.2));
    p = prevP;
    p.y += 0.012;
    d = max(abs(p.y) - 0.01, max(abs(p.x) - 0.27, d));
    return d;
}
#endif

#if ELEM_ID == 7
float elem_scifi_panel(vec2 p) {
    vec2 q = p * 1.2;

    float d = B(q, vec2(0.03));
    float a = radians(-45.0);
    float m = -dot(q - vec2(-0.005, 0.0), vec2(cos(a), sin(a)));
    d = max(m, d);
    m = dot(q - vec2(0.005, 0.0), vec2(cos(a), sin(a)));
    d = max(m, d);

    float d2 = B(q - vec2(0.175, 0.0256), vec2(0.15, 0.004));
    d = min(d, d2);
    d2 = B(q - vec2(-0.175, -0.0256), vec2(0.15, 0.004));
    d = abs(min(d, d2)) - 0.0005;

    vec2 qa = q;
    qa.y -= 0.003;
    qa.x += u_anim_t * 0.05;
    qa.x = mod(qa.x, 0.03) - 0.015;
    qa.x -= 0.01;
    d2 = B(qa, vec2(0.026));
    m = -dot(qa - vec2(-0.005, 0.0), vec2(cos(a), sin(a)));
    d2 = max(m, d2);
    m = dot(qa - vec2(0.005, 0.0), vec2(cos(a), sin(a)));
    d2 = max(m, d2);

    m = -dot(q - vec2(0.02, 0.0), vec2(cos(a), sin(a)));
    d2 = max(m, d2);
    m = dot(q - vec2(0.32, 0.0), vec2(cos(a), sin(a)));
    d2 = max(m, d2);
    d = min(d, d2);

    // Decorations anchored relative to one corner cluster in the original HUD.
    d2 = elem_tri_animation(p + vec2(-0.262, -0.08));
    d = min(d, d2);

    d2 = elem_random_dot_line(p + vec2(-0.12, -0.112));
    d = min(d, d2);

    return d;
}
#endif

#if ELEM_ID == 8
float elem_scifi_ui3_base(vec2 p) {
    float d = abs(length(p) - 0.03) - 0.01;
    p.x = abs(p.x) - 0.1;
    float d2 = abs(length(p) - 0.03) - 0.01;
    d = min(d, d2);
    return d;
}
#endif

#if ELEM_ID == 8
float elem_scifi_ui3(vec2 p) {
    vec2 prevP = p;
    float speed = 3.0;
    float d = abs(length(p) - 0.03) - 0.01;

    mat2 animRot = Rot(radians(u_anim_t * speed) * 40.0);
    p *= animRot;
    float a = radians(50.0);
    d = max(dot(p, vec2(cos(a), sin(a))), d);
    a = radians(-50.0);
    d = max(dot(p, vec2(cos(a), sin(a))), d);

    p = prevP;
    p.x = abs(p.x) - 0.1;
    animRot = Rot(radians(u_anim_t * speed) * 45.0);
    p *= animRot;
    float d2 = abs(length(p) - 0.03) - 0.01;
    a = radians(170.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);
    a = radians(-170.0);
    d2 = max(dot(p, vec2(cos(a), sin(a))), d2);

    return min(d, d2);
}
#endif

#if ELEM_ID == 5
float elem_slider(vec2 p) {
    vec2 prevP = p;
    float d = abs(B(p, vec2(0.15, 0.015))) - 0.001;
    float d2 = B(p - vec2(sin(u_anim_t * 1.5) * 0.13, 0.0), vec2(0.02, 0.013));
    d = min(d, d2);

    p.y = abs(p.y) - 0.045;
    d2 = abs(B(p, vec2(0.15, 0.015))) - 0.001;
    d = min(d, d2);
    d2 = B(p - vec2(sin(u_anim_t * 2.0) * -0.13, 0.0), vec2(0.02, 0.013));
    d = min(d, d2);

    p = prevP;
    p.y = abs(p.y);
    d2 = elem_scifi_ui(p - vec2(0.032, 0.045));
    d = min(d, d2);

    return d;
}
#endif

#if ELEM_ID == 6
float elem_graph(vec2 p) {
    vec2 prevP = p;
    float d = 10.0;
    float t = u_anim_t + Hash21(vec2(floor(p.y - 0.5), 0.0));
    p.y = abs(p.y);
    p.y += 0.127;
    for (float i = 1.0; i <= 16.0; i += 1.0) {
        float y = i * -0.015;
        float w = abs(sin(Hash21(vec2(i, 0.0)) * t * 3.0) * 0.1);
        float d2 = B(p + vec2(0.1 - w, y), vec2(w, 0.003));
        d = min(d, d2);
    }
    p = prevP;
    return max(abs(p.y) - 0.2, d);
}
#endif

float eval_widget(vec2 p, out float highlight_dist) {
    highlight_dist = 10.0;
#if ELEM_ID == 0
    return elem_main_wave(p);
#elif ELEM_ID == 1
    return elem_circle_dial(p);
#elif ELEM_ID == 2
    return elem_small_circle(p);
#elif ELEM_ID == 3
    return elem_small_circle2(p);
#elif ELEM_ID == 4
    return elem_barcode(p);
#elif ELEM_ID == 5
    return elem_slider(p);
#elif ELEM_ID == 6
    return elem_graph(p);
#elif ELEM_ID == 7
    return elem_scifi_panel(p);
#elif ELEM_ID == 8
    highlight_dist = elem_scifi_ui3_base(p);
    return elem_scifi_ui3(p);
#else
    return 10.0;
#endif
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    float anchor_x = u_res.x * u_offset_x;
    float anchor_y = u_res.y * u_offset_y;
    float norm = max(u_res.y, 1.0);
    vec2 uv = vec2(px - anchor_x, anchor_y - py) / norm;

    float a = radians(u_angle);
    uv *= Rot(a);
    uv /= max(u_scale, 0.001);
    uv.x += ELEM_ANCHOR.x;
    uv.y -= ELEM_ANCHOR.y;

    vec2 uv_cull = uv - vec2(ELEM_ANCHOR.x, -ELEM_ANCHOR.y);
    if (u_bound_r > 0.0 && dot(uv_cull, uv_cull) > u_bound_r * u_bound_r) {
        frag_color = vec4(0.0);
        return;
    }

    float hi_dist;
    float d = eval_widget(uv, hi_dist);

    float aa = 1.0 / min(u_res.y, u_res.x);
    if (d > aa * 4.0 && hi_dist > aa * 4.0) {
        frag_color = vec4(0.0);
        return;
    }

    vec3 col = vec3(0.0);
    vec3 hi_col = mix(u_color, vec3(1.0), 0.35) * u_brightness;
    vec3 fg_col = u_color * u_brightness;

    float edge = 0.0;
#if ELEM_ID == 0
    edge = -0.005;
#endif

#if ELEM_ID == 8
    col = mix(col, hi_col, S(hi_dist, edge, aa));
    col = mix(col, fg_col, S(d, edge, aa));
#else
    col = mix(col, fg_col, S(d, edge, aa));
#endif

    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class SciFiWidgetGL(AudioVisualMixin, ClipGL):
    """Single sci-fi HUD widget rendered via SDF — pick one widget, position it, optional bus reactivity."""

    clip_type: ClassVar[str] = "std-scifi-widget-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="center_dial",
            label="Center Dial",
            values={
                "widget": "circle_dial",
                "offset_x": 0.5,
                "offset_y": 0.5,
                "scale": 1.0,
                "speed": 1.0,
                "angle": 0.0,
                "opacity": 1.0,
                "luma_alpha": 0.4,
            },
        ),
        ClipPreset(
            id="corner_slider",
            label="Corner Slider",
            values={
                "widget": "slider",
                "color": "secondary",
                "offset_x": 0.88,
                "offset_y": 0.92,
                "scale": 1.55,
                "sensitivity": 0.30,
                "speed": 1.0,
                "angle": 90,
                "opacity": 1.0,
                "luma_alpha": 0.4,
            },
        ),
    ]

    widget: SciFiWidgetKind = Field(
        default="circle_dial",
        description="Which HUD widget to render",
        json_schema_extra={"label": "Widget"},
    )
    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal position (0 = left, 0.5 = center, 1 = right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical position (0 = top, 0.5 = center, 1 = bottom)",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier",
    )
    scale: float = Field(
        default=1.0,
        ge=0.25,
        le=3.0,
        multiple_of=0.05,
        description="Uniform widget scale",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on amplitude brightness after job-wide normalization",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid, 1 = dark areas transparent)",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _programs: dict[int, tuple[moderngl.Program, moderngl.VertexArray]] = PrivateAttr(
        default_factory=dict
    )

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

        bus = self.bus_timeline(ctx)
        total = max(ctx.job.total_frames, 0)
        _, _, _, self._amp_history = precompute_bus_drives(bus, total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name not in prog:
            return
        cast(moderngl.Uniform, prog[name]).value = value

    def _amp_drive_for_frame(self, ctx: RenderContext) -> float:
        if not self.bus_active_for_draw(ctx):
            return 0.0
        sens = float(self.sensitivity)
        if self._amp_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._amp_history.shape[0] - 1))
            return min(1.0, float(self._amp_history[f]) * sens)
        return self.scale_audio(float(ctx.audio_bus_frame.amplitude))

    def _bound_radius(self) -> float:
        base = _WIDGET_HIT_RADIUS[self.widget]
        if base <= 0.0:
            return 0.0
        # Cull runs in post-scale widget UV (extent is scale-invariant there).
        return base * 1.15

    def _get_program(
        self, gl: moderngl.Context, elem_id: int
    ) -> tuple[moderngl.Program, moderngl.VertexArray]:
        cached = self._programs.get(elem_id)
        if cached is not None:
            return cached
        src = _frag_for_widget_kind(elem_id)
        prog = gl.program(vertex_shader=_VERT, fragment_shader=src)
        vbo = gl.buffer(_QUAD.tobytes())
        vao = gl.simple_vertex_array(prog, vbo, "in_vert")
        self._programs[elem_id] = (prog, vao)
        return prog, vao

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas
        elem_id = _WIDGET_KIND_IDS[self.widget]
        prog, vao = self._get_program(gl, elem_id)

        amp = self._amp_drive_for_frame(ctx)
        brightness = 1.0 + amp * 0.25

        r, g, b, _ = resolve_color(self.color, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_anim_t", ctx.time.t * self.speed)
        self._set_uniform(prog, "u_bound_r", self._bound_radius())
        self._set_uniform(prog, "u_color", (r, g, b))
        self._set_uniform(prog, "u_offset_x", self.offset_x)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_scale", self.scale)
        self._set_uniform(prog, "u_angle", self.angle)
        self._set_uniform(prog, "u_brightness", brightness)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        vao.render(moderngl.TRIANGLES)

        gl.scissor = None
