from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pixfabrica_core.catalog import CatalogCache
from pixfabrica_core.clips import RenderJob
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.load_render_job import load_render_job, parse_render_job_data
from pixfabrica_core.project_bundles.detect import is_bundle_file
from pixfabrica_core.project_bundles.errors import BundleImportError
from pixfabrica_core.project_bundles.export import strip_host_local_fields
from pixfabrica_core.project_bundles.import_bundle import import_project_bundle
from pixfabrica_core.project_bundles.refs import collect_media_refs

log = logging.getLogger(__name__)


def bundle_import_error_to_render_error(exc: BundleImportError) -> RenderError:
    message = exc.message
    lowered = message.lower()
    if "missing" in lowered or "not bundled" in lowered:
        return RenderError(
            RenderErrorCode.MISSING_ASSET,
            {"path": "<bundle>", "detail": message},
        )
    return RenderError(
        RenderErrorCode.INVALID_PARAMETER,
        {"field": "<bundle>", "msg": message},
    )


def _warn_remote_bundle_sources(project: dict[str, Any], catalog: CatalogCache) -> None:
    for ref in collect_media_refs(project, catalog, remote_only=True):
        log.warning(
            "bundle contains remote source %r — render may fail offline",
            ref.source_value,
        )


@contextmanager
def open_render_job(path: Path, *, catalog: CatalogCache) -> Iterator[RenderJob]:
    """Load a RenderJob from plain JSON or a portable .pixfabrica.zip bundle.

    For bundles, assets are extracted to an ephemeral temp directory that is
    removed when the context exits.
    """
    resolved = path.resolve()

    if resolved.suffix.lower() == ".zip":
        if not is_bundle_file(resolved):
            raise RenderError(
                RenderErrorCode.INVALID_PARAMETER,
                {
                    "field": "<bundle>",
                    "msg": "file is not a pixfabrica bundle (missing or invalid bundle.json)",
                },
            )

        temp_dir = Path(tempfile.mkdtemp(prefix="pixfabrica-bundle-"))
        try:
            try:
                zip_bytes = resolved.read_bytes()
            except OSError as exc:
                raise RenderError(
                    RenderErrorCode.MISSING_ASSET,
                    {"path": str(resolved), "detail": str(exc)},
                ) from exc

            try:
                project = import_project_bundle(
                    zip_bytes,
                    bundle_dir=temp_dir,
                    catalog=catalog,
                )
            except BundleImportError as exc:
                raise bundle_import_error_to_render_error(exc) from exc

            _warn_remote_bundle_sources(project, catalog)
            strip_host_local_fields(project)
            yield parse_render_job_data(project)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return

    yield load_render_job(resolved)
