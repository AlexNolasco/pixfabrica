"""Bundle export/import errors."""

from __future__ import annotations


class BundleExportError(Exception):
    def __init__(self, *, missing_files: list[str]) -> None:
        self.missing_files = missing_files
        super().__init__(f"missing {len(missing_files)} bundled asset(s)")


class BundleImportError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
