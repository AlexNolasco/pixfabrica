"""Parent-only job asset phase — runs before track ``prepare()`` / worker pool.

Plugins declare contributors on their ``Plugin`` class::

    class Plugin:
        job_asset_contributors = [MyContributor]  # class objects

    # or dotted strings:
        job_asset_contributors = ["my_pkg.assets:MyContributor"]

Each contributor implements :class:`JobAssetContributor`: ``applies`` decides
whether work is needed for this job; ``materialize`` does blocking I/O (the
renderer runs it in a thread pool).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pixfabrica_core.clips import PrepareContext, RenderJob

log = logging.getLogger("pixfabrica_core.job_assets")


@runtime_checkable
class JobAssetContributor(Protocol):
    """Optional plugin hook — parent process only, before visual ``prepare()``."""

    @classmethod
    def applies(cls, job: RenderJob) -> bool: ...

    @classmethod
    def materialize(cls, job: RenderJob, ctx: PrepareContext) -> None: ...


def _resolve_contributor_ref(ref: Any) -> type[JobAssetContributor]:
    if isinstance(ref, type):
        return ref  # type: ignore[return-value]
    if ":" in ref:
        mod_name, _, attr = ref.partition(":")
    else:
        mod_name, _, attr = ref.rpartition(".")
        if not mod_name or not attr:
            raise ValueError(f"invalid job_asset_contributor ref: {ref!r}")
    module = importlib.import_module(mod_name)
    cls = getattr(module, attr)
    if not isinstance(cls, type):
        raise TypeError(f"job_asset_contributor {ref!r} is not a type")
    return cls  # type: ignore[return-value]


def iter_job_asset_contributor_classes(discovered: list[Any]) -> list[type[JobAssetContributor]]:
    seen: set[type[JobAssetContributor]] = set()
    out: list[type[JobAssetContributor]] = []
    for plug in discovered:
        raw = getattr(plug.plugin_class, "job_asset_contributors", None) or []
        for ref in raw:
            cls = _resolve_contributor_ref(ref)
            if cls not in seen:
                seen.add(cls)
                out.append(cls)
    return out


async def run_job_asset_contributor_phase(
    job: RenderJob,
    ctx: PrepareContext,
    discovered: list[Any],
) -> None:
    """Run every registered contributor whose ``applies(job)`` is true."""
    classes = iter_job_asset_contributor_classes(discovered)
    for cls in classes:
        if not cls.applies(job):
            continue
        log.info("job assets: materializing via %s", cls.__name__)
        await asyncio.to_thread(cls.materialize, job, ctx)
