import type { JobColorPalette } from '@/lib/jobColors'

export interface ThemePresetEntry {
  theme: string
  variant: 'dark' | 'light'
  label: string
  colors: JobColorPalette
}

export const FALLBACK_THEME_PRESETS: ThemePresetEntry[] = [
  {
    "theme": "amber",
    "variant": "dark",
    "label": "Amber (Dark)",
    "colors": {
      "primary": "#f1c371",
      "secondary": "#f8efaf",
      "tertiary": "#c99023",
      "accent": "#ff9f43",
      "background": "#231b10",
      "neutral": "#e1dcc5",
      "neutral_variant": "#8b6b40"
    }
  },
  {
    "theme": "amber",
    "variant": "light",
    "label": "Amber (Light)",
    "colors": {
      "primary": "#b87a10",
      "secondary": "#d4a520",
      "tertiary": "#7a4e05",
      "accent": "#e05c10",
      "background": "#faf5eb",
      "neutral": "#1a1208",
      "neutral_variant": "#6b4820"
    }
  },
  {
    "theme": "violet",
    "variant": "dark",
    "label": "Violet (Dark)",
    "colors": {
      "primary": "#b39ddb",
      "secondary": "#9575cd",
      "tertiary": "#7e57c2",
      "accent": "#ea80fc",
      "background": "#1a1228",
      "neutral": "#ede7f6",
      "neutral_variant": "#5e35b1"
    }
  },
  {
    "theme": "violet",
    "variant": "light",
    "label": "Violet (Light)",
    "colors": {
      "primary": "#7e57c2",
      "secondary": "#5e35b1",
      "tertiary": "#4527a0",
      "accent": "#d500f9",
      "background": "#f3e5f5",
      "neutral": "#1a0533",
      "neutral_variant": "#9c27b0"
    }
  },
  {
    "theme": "rose",
    "variant": "dark",
    "label": "Rose (Dark)",
    "colors": {
      "primary": "#f48fb1",
      "secondary": "#f06292",
      "tertiary": "#c2185b",
      "accent": "#ff4081",
      "background": "#1a0d10",
      "neutral": "#fce4ec",
      "neutral_variant": "#880e4f"
    }
  },
  {
    "theme": "rose",
    "variant": "light",
    "label": "Rose (Light)",
    "colors": {
      "primary": "#e91e63",
      "secondary": "#f06292",
      "tertiary": "#ad1457",
      "accent": "#f50057",
      "background": "#fff0f5",
      "neutral": "#1a0010",
      "neutral_variant": "#6d2040"
    }
  },
  {
    "theme": "emerald",
    "variant": "dark",
    "label": "Emerald (Dark)",
    "colors": {
      "primary": "#80cbc4",
      "secondary": "#4db6ac",
      "tertiary": "#26a69a",
      "accent": "#64ffda",
      "background": "#0d1f1e",
      "neutral": "#e0f2f1",
      "neutral_variant": "#00796b"
    }
  },
  {
    "theme": "emerald",
    "variant": "light",
    "label": "Emerald (Light)",
    "colors": {
      "primary": "#2e7d32",
      "secondary": "#388e3c",
      "tertiary": "#1b5e20",
      "accent": "#00c853",
      "background": "#f1f8e9",
      "neutral": "#1b2016",
      "neutral_variant": "#558b2f"
    }
  },
  {
    "theme": "slate",
    "variant": "dark",
    "label": "Slate (Dark)",
    "colors": {
      "primary": "#90a4ae",
      "secondary": "#78909c",
      "tertiary": "#546e7a",
      "accent": "#84ffff",
      "background": "#0f1923",
      "neutral": "#eceff1",
      "neutral_variant": "#455a64"
    }
  },
  {
    "theme": "slate",
    "variant": "light",
    "label": "Slate (Light)",
    "colors": {
      "primary": "#455a64",
      "secondary": "#607d8b",
      "tertiary": "#263238",
      "accent": "#0097a7",
      "background": "#eceff1",
      "neutral": "#102027",
      "neutral_variant": "#78909c"
    }
  },
  {
    "theme": "sky",
    "variant": "dark",
    "label": "Sky (Dark)",
    "colors": {
      "primary": "#81d4fa",
      "secondary": "#29b6f6",
      "tertiary": "#01579b",
      "accent": "#00e5ff",
      "background": "#0a1929",
      "neutral": "#e1f5fe",
      "neutral_variant": "#0288d1"
    }
  },
  {
    "theme": "sky",
    "variant": "light",
    "label": "Sky (Light)",
    "colors": {
      "primary": "#0288d1",
      "secondary": "#039be5",
      "tertiary": "#01579b",
      "accent": "#00b0ff",
      "background": "#e1f5fe",
      "neutral": "#0a1929",
      "neutral_variant": "#4fc3f7"
    }
  },
  {
    "theme": "gold",
    "variant": "dark",
    "label": "Gold (Dark)",
    "colors": {
      "primary": "#e8c597",
      "secondary": "#cd9b47",
      "tertiary": "#8c6520",
      "accent": "#ffe0a3",
      "background": "#121c21",
      "neutral": "#f0e6d3",
      "neutral_variant": "#4e7d95"
    }
  },
  {
    "theme": "gold",
    "variant": "light",
    "label": "Gold (Light)",
    "colors": {
      "primary": "#8c6520",
      "secondary": "#a07828",
      "tertiary": "#5a3f0a",
      "accent": "#cd9b47",
      "background": "#fdf8f0",
      "neutral": "#1a1000",
      "neutral_variant": "#c9a555"
    }
  },
  {
    "theme": "midnight",
    "variant": "dark",
    "label": "Midnight (Dark)",
    "colors": {
      "primary": "#b0bec5",
      "secondary": "#78909c",
      "tertiary": "#546e7a",
      "accent": "#90caf9",
      "background": "#050a0e",
      "neutral": "#eceff1",
      "neutral_variant": "#37474f"
    }
  },
  {
    "theme": "midnight",
    "variant": "light",
    "label": "Midnight (Light)",
    "colors": {
      "primary": "#455a64",
      "secondary": "#607d8b",
      "tertiary": "#263238",
      "accent": "#1565c0",
      "background": "#fafafa",
      "neutral": "#1c1c1c",
      "neutral_variant": "#9e9e9e"
    }
  }
]
