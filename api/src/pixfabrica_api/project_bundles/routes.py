"""HTTP routes for portable project bundles."""

from __future__ import annotations

import uuid
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from pixfabrica_api.catalog_cache import get_catalog_cache
from pixfabrica_api.gl_policy import validate_graph_gl_policy
from pixfabrica_api.license_policy import validate_graph_license_policy
from pixfabrica_api.media_settings import media_root
from pixfabrica_core.fonts import clear_skia_font_cache, rebuild_font_catalog
from pixfabrica_core.fonts.manifest import FontManifestError
from pixfabrica_core.project_bundles.errors import BundleExportError, BundleImportError
from pixfabrica_core.project_bundles.export import export_project_bundle
from pixfabrica_core.project_bundles.import_bundle import import_project_bundle

router = APIRouter(prefix="/project-bundles", tags=["project-bundles"])

BundleUpload = Annotated[UploadFile, File()]


class BundleExportRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None


class BundleImportResponse(BaseModel):
    project: dict[str, Any] = Field(description="Web project JSON with rewritten local paths")
    import_bundle_id: str = Field(description="Host-local bundle folder id under media/bundles/")


class BundleExportMissingResponse(BaseModel):
    missing_files: list[str]


@router.post("/export")
async def export_bundle(body: BundleExportRequest) -> Response:
    project = body.model_dump(mode="json")
    try:
        payload, filename = export_project_bundle(
            project,
            media_root=media_root(),
            catalog=get_catalog_cache(),
        )
    except BundleExportError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_assets",
                "missing_files": exc.missing_files,
            },
        ) from exc

    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=BundleImportResponse)
async def import_bundle(file: BundleUpload) -> BundleImportResponse:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")

    import_id = str(uuid.uuid4())
    bundle_dir = (media_root() / "bundles" / import_id).resolve()

    try:
        project = import_project_bundle(
            raw,
            bundle_dir=bundle_dir,
            catalog=get_catalog_cache(),
            assign_import_bundle_id=True,
            import_bundle_id=import_id,
        )
    except BundleImportError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    with suppress(FontManifestError):
        rebuild_font_catalog()
    clear_skia_font_cache()

    try:
        validate_graph_gl_policy(project)
        validate_graph_license_policy(project)
    except HTTPException:
        raise

    import_id_from_project = project.pop("import_bundle_id", None)
    if not isinstance(import_id_from_project, str) or not import_id_from_project:
        raise HTTPException(status_code=500, detail="import did not assign bundle id")

    return BundleImportResponse(project=project, import_bundle_id=import_id_from_project)
