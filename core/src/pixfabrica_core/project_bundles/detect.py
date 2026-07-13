"""Detect portable Pixfabrica bundle archives."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from pixfabrica_core.project_bundles.format import BUNDLE_MANIFEST_NAME, validate_bundle_manifest


def is_bundle_file(path: Path) -> bool:
    if path.suffix.lower() != ".zip":
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            if BUNDLE_MANIFEST_NAME not in archive.namelist():
                return False
            manifest_raw = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
            validate_bundle_manifest(manifest_raw)
            return True
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, ValueError):
        return False
