#!/usr/bin/env python3
"""Audit std clips for preview vs export motion parity (px/s at output resolution).

Detects clips that use absolute pixel speeds against geometry that scales with
canvas size without scaling speed by surface_height / design_height.

Run from repo root:
    uv run python scripts/audit_preview_motion_parity.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STD_SRC = ROOT / "plugins" / "std" / "src" / "pixfabrica_std"

# Heuristic code patterns (same bug class as marquee).
PIXEL_MOTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "scroll_mod_period",
        re.compile(r"(?:ctx\.time\.t|u_t|\bt\b)\s*\*\s*.*speed.*%\s*.*period", re.I),
    ),
    ("shader_mod_period", re.compile(r"mod\s*\(\s*u_t\s*\*\s*u_speed\s*,\s*u_period\s*\)", re.I)),
    ("shader_perimeter", re.compile(r"mod\s*\(\s*u_t\s*\*\s*\(\s*u_speed", re.I)),
    ("trajectory_dt", re.compile(r"layout\.speed\s*\*\s*dt|speed\s*\*\s*dt", re.I)),
    ("velocity_times_t", re.compile(r"(?:vx|vy)\s*\*\s*t\b", re.I)),
]

PX_S_DESC = re.compile(r"px/s|px/second", re.I)
USES_DESIGN_SCALE = re.compile(
    r"design_height|design_width|scale_output_px",
    re.I,
)

# GL clips where u_t * u_speed is typically UV/phase animation (lower risk).
GL_PHASE_ONLY_HINTS = re.compile(
    r"u_eff_t|iTime|speed_t|realTime|fbm\(|NetLayer|rot2\(|shadertoy",
    re.I,
)


@dataclass
class ClipFinding:
    clip_type: str
    module: str
    risk: str
    reasons: list[str] = field(default_factory=list)
    px_s_fields: list[str] = field(default_factory=list)
    motion_patterns: list[str] = field(default_factory=list)
    uses_design_scale: bool = False


def _clip_type_from_path(path: Path) -> str | None:
    for parent in path.parents:
        if parent.name == "pixfabrica_std":
            break
    try:
        rel = path.relative_to(STD_SRC)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    return f"std-{parts[-1].replace('.py', '').replace('_', '-')}"


def _find_clip_type_in_source(text: str, fallback: str) -> str:
    m = re.search(r'clip_type:\s*ClassVar\[str\]\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else fallback


def _px_s_field_names(text: str) -> list[str]:
    names: list[str] = []
    for m in re.finditer(
        r"(\w+):\s*float\s*=\s*Field\([^)]*description=[^)]*(?:px/s|px/second)",
        text,
        re.I | re.DOTALL,
    ):
        names.append(m.group(1))
    return names


def audit_file(path: Path) -> ClipFinding | None:
    text = path.read_text(encoding="utf-8")
    if "clip_type" not in text and "ClipSkia" not in text and "ClipGL" not in text:
        return None

    fallback = _clip_type_from_path(path) or path.stem
    clip_type = _find_clip_type_in_source(text, fallback)
    px_s_fields = _px_s_field_names(text)
    motion_patterns = [name for name, pat in PIXEL_MOTION_PATTERNS if pat.search(text)]
    uses_design_scale = bool(USES_DESIGN_SCALE.search(text))

    if not px_s_fields and not motion_patterns:
        return None

    reasons: list[str] = []
    risk = "low"

    has_pixel_loop = bool(
        set(motion_patterns)
        & {
            "scroll_mod_period",
            "shader_mod_period",
            "shader_perimeter",
            "trajectory_dt",
            "velocity_times_t",
        }
    )

    if px_s_fields and has_pixel_loop and not uses_design_scale:
        risk = "high"
        reasons.append("px/s param + pixel-period motion, no design_height scaling")
    elif px_s_fields and not uses_design_scale:
        risk = "medium"
        reasons.append("px/s param declared, no design_height scaling in module")
    elif has_pixel_loop and not uses_design_scale:
        risk = "medium"
        reasons.append("pixel motion pattern without design_height scaling")
    elif uses_design_scale:
        risk = "fixed"
        reasons.append("uses design_height / output resolution scaling")
    else:
        reasons.append("informational only")

    if (
        path.suffix == ".py"
        and "_gl.py" in path.name
        and risk == "medium"
        and re.search(r"ctx\.time\.t\s*\*\s*self\.speed|u_t\s*\*\s*u_speed", text)
        and GL_PHASE_ONLY_HINTS.search(text)
    ):
        risk = "low"
        reasons.append("GL shader likely uses speed as UV/phase multiplier")

    return ClipFinding(
        clip_type=clip_type,
        module=str(path.relative_to(ROOT)),
        risk=risk,
        reasons=reasons,
        px_s_fields=px_s_fields,
        motion_patterns=motion_patterns,
        uses_design_scale=uses_design_scale,
    )


def run_numeric_parity_checks() -> list[tuple[str, str, bool, str]]:
    """Return (clip, check_name, passed, detail) for computable parity cases."""

    from pixfabrica_core.clips import JobInfo
    from pixfabrica_core.preview_dims import (
        DEFAULT_REFERENCE_HEIGHT,
        preview_dimensions,
        scale_typography_for_job_height,
    )
    from pixfabrica_core.theme.color import ColorPalette
    from pixfabrica_core.theme.typography import FontPalette
    from pixfabrica_std.text.skia_font import make_typography_font

    job_w, job_h = 1920, 1080
    preview_w, preview_h = preview_dimensions(job_w, job_h)
    t = 2.0
    results: list[tuple[str, str, bool, str]] = []

    def job(surface_w: int, surface_h: int, typo: FontPalette) -> JobInfo:
        return JobInfo(
            title="t",
            description="d",
            width=surface_w,
            height=surface_h,
            fps=30.0,
            duration=8.0,
            colors=ColorPalette(),
            typography=typo,
            locale="en",
            output_width=job_w,
            output_height=job_h,
        )

    base = FontPalette()
    export_typo = scale_typography_for_job_height(
        base, job_height=job_h, reference_height=DEFAULT_REFERENCE_HEIGHT
    )
    preview_typo = export_typo.scale(preview_h / job_h)

    # --- marquee (fixed): should match ---
    from pixfabrica_std.text.marquee import Marquee

    text = "My Song Title"
    m = Marquee(id="a", speed=100.0, text=text, typography_role="title_large")

    def marquee_phase(with_fix: bool) -> tuple[float, float]:
        def eff_speed(j: JobInfo) -> float:
            if with_fix:
                return j.scale_output_px(m.speed)
            return m.speed

        def period(typo: FontPalette) -> float:
            spec = typo.title_large
            font = make_typography_font(spec)
            font.setLinearMetrics(True)
            return font.measureText(text) + spec.size

        ej = job(job_w, job_h, export_typo)
        pj = job(preview_w, preview_h, preview_typo)
        ep = (t * eff_speed(ej)) % period(export_typo) / period(export_typo)
        pp = (t * eff_speed(pj)) % period(preview_typo) / period(preview_typo)
        return ep, pp

    ep, pp = marquee_phase(with_fix=True)
    results.append(
        (
            "std-marquee",
            "phase_fraction@fix",
            abs(ep - pp) < 0.001,
            f"export={ep:.4f} preview={pp:.4f}",
        )
    )

    def raw_marquee_phase() -> tuple[float, float]:
        def period(typo: FontPalette) -> float:
            spec = typo.title_large
            font = make_typography_font(spec)
            font.setLinearMetrics(True)
            return font.measureText(text) + spec.size

        ep = (t * m.speed) % period(export_typo) / period(export_typo)
        pp = (t * m.speed) % period(preview_typo) / period(preview_typo)
        return ep, pp

    ep2, pp2 = raw_marquee_phase()
    results.append(
        (
            "std-marquee",
            "phase_fraction@unfixed",
            abs(ep2 - pp2) > 0.03,
            f"export={ep2:.4f} preview={pp2:.4f} (4x faster in preview)",
        )
    )

    # --- sweep_lines (unfixed): period scales with bounds width ---
    def sweep_phase(surf_w: int, surf_h: int, *, scaled: bool) -> float:
        half_len = surf_w * 0.1
        period = surf_w + 2 * half_len
        eff = speed * (surf_h / job_h) if scaled else speed
        return (t * eff) % period / period

    speed = 200.0
    ep = sweep_phase(job_w, job_h, scaled=False)
    pp = sweep_phase(preview_w, preview_h, scaled=False)
    results.append(
        (
            "std-sweep-lines",
            "phase_fraction@unfixed",
            abs(ep - pp) > 0.1,
            f"export={ep:.4f} preview={pp:.4f}",
        )
    )
    ep = sweep_phase(job_w, job_h, scaled=True)
    pp = sweep_phase(preview_w, preview_h, scaled=True)
    results.append(
        (
            "std-sweep-lines",
            "phase_fraction@scaled",
            abs(ep - pp) < 0.001,
            f"export={ep:.4f} preview={pp:.4f}",
        )
    )

    # --- border plasma perimeter ---
    def border_phase(w: int, h: int, *, scaled: bool) -> float:
        per = 4.0 * (w + h)
        eff = speed * (h / job_h) if scaled else speed
        return (t * eff) % per / per

    speed = 400.0
    ep = border_phase(job_w, job_h, scaled=False)
    pp = border_phase(preview_w, preview_h, scaled=False)
    results.append(
        (
            "std-border-plasma-gl",
            "perimeter_phase@unfixed",
            abs(ep - pp) > 0.1,
            f"export={ep:.4f} preview={pp:.4f}",
        )
    )
    ep = border_phase(job_w, job_h, scaled=True)
    pp = border_phase(preview_w, preview_h, scaled=True)
    results.append(
        (
            "std-border-plasma-gl",
            "perimeter_phase@scaled",
            abs(ep - pp) < 0.001,
            f"export={ep:.4f} preview={pp:.4f}",
        )
    )

    # --- cloud: cross-screen time (wrap width scales) ---
    def cloud_phase(w: int, h: int, *, scaled: bool) -> float:
        wrap = w * 1.5
        eff_vx = vx * (h / job_h) if scaled else vx
        return (eff_vx * t) % wrap / wrap

    vx = 5.0
    ep = cloud_phase(job_w, job_h, scaled=False)
    pp = cloud_phase(preview_w, preview_h, scaled=False)
    results.append(
        (
            "std-cloud",
            "wrap_phase@unfixed",
            pp / ep > 3.5 if ep > 0 else pp > ep,
            f"export={ep:.4f} preview={pp:.4f} (~{pp / ep:.1f}x faster in preview)"
            if ep
            else f"preview={pp:.4f}",
        )
    )

    return results


def main() -> int:
    findings: list[ClipFinding] = []
    for path in sorted(STD_SRC.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        finding = audit_file(path)
        if finding:
            findings.append(finding)

    order = {"high": 0, "medium": 1, "low": 2, "fixed": 3}
    findings.sort(key=lambda f: (order.get(f.risk, 9), f.clip_type))

    print("=" * 72)
    print("Preview / export motion parity audit (plugins/std)")
    print("=" * 72)
    print()

    for risk in ("high", "medium", "low", "fixed"):
        group = [f for f in findings if f.risk == risk]
        if not group:
            continue
        print(f"## {risk.upper()} ({len(group)})")
        print()
        for f in group:
            print(f"  {f.clip_type}")
            print(f"    module: {f.module}")
            if f.px_s_fields:
                print(f"    px/s fields: {', '.join(f.px_s_fields)}")
            if f.motion_patterns:
                print(f"    patterns: {', '.join(f.motion_patterns)}")
            for r in f.reasons:
                print(f"    - {r}")
            print()

    print("=" * 72)
    print("Numeric parity checks (1080p export vs capped preview)")
    print("=" * 72)
    print()
    try:
        for clip, check, passed, detail in run_numeric_parity_checks():
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {clip} :: {check}")
            print(f"         {detail}")
        print()
    except Exception as exc:
        print(f"  Numeric checks skipped: {exc}")
        print()

    high = [f.clip_type for f in findings if f.risk == "high"]
    print("=" * 72)
    print(f"Summary: {len(findings)} modules flagged; {len(high)} high-risk clip(s)")
    if high:
        print("High-risk:", ", ".join(high))
    print("=" * 72)
    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main())
