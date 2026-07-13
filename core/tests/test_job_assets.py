from pathlib import Path

from pixfabrica_core.job_assets import iter_job_asset_contributor_classes
from pixfabrica_core.plugins.discovery import DiscoveredPlugin


class _ContribA:
    @classmethod
    def applies(cls, job):
        return False

    @classmethod
    def materialize(cls, job, ctx):
        pass


class _PluginDup:
    job_asset_contributors = [_ContribA, "test_job_assets:_ContribA"]


def test_iter_job_asset_contributor_classes_dedupes_string_and_type():
    plug = DiscoveredPlugin(
        package_name="p",
        version="0",
        author=None,
        plugin_class=_PluginDup,
        plugin_package_dir=Path("."),
    )
    classes = iter_job_asset_contributor_classes([plug])
    assert len(classes) == 1
    assert classes[0] is _ContribA
