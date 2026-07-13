"""Host catalog policy — excluded SPDX licenses from pixfabrica.toml or env."""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent.parent / "pixfabrica.toml"
_ENV_EXCLUDED = "PIXFABRICA_CATALOG_EXCLUDED_LICENSES"


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _parse_license_list(raw: object) -> frozenset[str]:
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",")]
        return frozenset(part for part in parts if part)
    if isinstance(raw, list):
        return frozenset(str(item).strip() for item in raw if str(item).strip())
    return frozenset()


@lru_cache(maxsize=1)
def load_excluded_licenses() -> frozenset[str]:
    """Return SPDX ids excluded from the active catalog (env overrides TOML)."""
    env_raw = os.environ.get(_ENV_EXCLUDED, "").strip()
    if env_raw:
        return _parse_license_list(env_raw)
    config = _load_config()
    catalog_cfg = config.get("catalog", {})
    if isinstance(catalog_cfg, dict):
        return _parse_license_list(catalog_cfg.get("excluded_licenses", []))
    return frozenset()


def catalog_policy_payload() -> dict[str, list[str]]:
    excluded = sorted(load_excluded_licenses())
    return {"excluded_licenses": excluded}
