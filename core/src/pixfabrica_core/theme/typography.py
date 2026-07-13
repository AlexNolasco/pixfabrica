from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FontRole = Literal[
    "display_large",
    "display_medium",
    "display_small",
    "title_large",
    "title_medium",
    "title_small",
    "body_large",
    "body_medium",
    "body_small",
    "label_large",
    "label_medium",
    "label_small",
    "mono_large",
    "mono_medium",
    "mono_small",
]


class FontSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    family: str = "Inter"
    weight: int = Field(default=500, ge=100, le=900)  # Shifted default to Medium for video safety
    size: float = Field(default=29.0, gt=0)
    line_height: float = Field(default=1.24, gt=0)
    letter_spacing: float = 0.0
    color: str = "neutral"

    def scale(self, factor: float) -> FontSpec:
        return self.model_copy(update={"size": self.size * factor})


class FontPalette(BaseModel):
    model_config = ConfigDict(frozen=True)

    # --- 1. DISPLAY (Hero Scale) ---
    # Apple tvOS tops out at 76. For full-frame video intros, we extrapolate upward.
    display_large: FontSpec = Field(
        default_factory=lambda: FontSpec(
            size=114.0, weight=800, line_height=1.1, letter_spacing=-1.0
        )
    )
    display_medium: FontSpec = Field(
        default_factory=lambda: FontSpec(
            size=96.0, weight=700, line_height=1.15, letter_spacing=-0.5
        )
    )
    display_small: FontSpec = Field(
        default_factory=lambda: FontSpec(
            size=76.0, weight=700, line_height=1.26
        )  # Matches tvOS Title 1 (Emphasized)
    )

    # --- 2. TITLE (Structural Scale) ---
    title_large: FontSpec = Field(
        default_factory=lambda: FontSpec(
            size=76.0, weight=500, line_height=1.26
        )  # tvOS Title 1 (Standard)
    )
    title_medium: FontSpec = Field(
        default_factory=lambda: FontSpec(size=57.0, weight=500, line_height=1.15)  # tvOS Title 2
    )
    title_small: FontSpec = Field(
        default_factory=lambda: FontSpec(size=48.0, weight=500, line_height=1.16)  # tvOS Title 3
    )

    # --- 3. BODY (Reading Scale) ---
    body_large: FontSpec = Field(
        default_factory=lambda: FontSpec(size=38.0, weight=500, line_height=1.21)  # tvOS Headline
    )
    body_medium: FontSpec = Field(
        default_factory=lambda: FontSpec(size=29.0, weight=500, line_height=1.24)  # tvOS Body
    )
    body_small: FontSpec = Field(
        default_factory=lambda: FontSpec(size=25.0, weight=500, line_height=1.28)  # tvOS Caption 1
    )

    # --- 4. LABEL (Interface & Utility Scale) ---
    label_large: FontSpec = Field(
        default_factory=lambda: FontSpec(
            size=38.0, weight=400, line_height=1.21
        )  # tvOS Subtitle 1 (Notice weight is 400 here)
    )
    label_medium: FontSpec = Field(
        default_factory=lambda: FontSpec(size=31.0, weight=500, line_height=1.22)  # tvOS Callout
    )
    label_small: FontSpec = Field(
        default_factory=lambda: FontSpec(size=23.0, weight=500, line_height=1.3)  # tvOS Caption 2
    )

    # --- 5. MONOSPACE (Data & Debug Scale) ---
    # Aligned to tvOS Body, Callout, and Caption 2 sizes for rhythm
    mono_large: FontSpec = Field(
        default_factory=lambda: FontSpec(
            family="JetBrains Mono", size=38.0, weight=400, line_height=1.2
        )
    )
    mono_medium: FontSpec = Field(
        default_factory=lambda: FontSpec(
            family="JetBrains Mono", size=29.0, weight=400, line_height=1.2
        )
    )
    mono_small: FontSpec = Field(
        default_factory=lambda: FontSpec(
            family="JetBrains Mono", size=23.0, weight=400, line_height=1.2
        )
    )

    def scale(self, factor: float) -> FontPalette:
        scaled_fonts = {
            field_name: getattr(self, field_name).scale(factor)
            for field_name in self.__class__.model_fields
        }
        return self.model_copy(update=scaled_fonts)
