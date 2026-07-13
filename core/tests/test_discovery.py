from pathlib import Path

from pixfabrica_core.plugins.discovery import DiscoveredPlugin, discover_plugins

# ── Fixtures ──────────────────────────────────────────────────────────────────

GOOD_PLUGIN_TOML = """\
[project]
name = "acme-rain"
version = "1.2.3"
authors = [{name = "Jane", email = "jane@acme.com"}]
"""

GOOD_PLUGIN_INIT = """\
from pixfabrica_core.plugins import PluginManifest

class Plugin:
    manifest = PluginManifest(
        name="acme-rain",
        display_name="Acme Rain",
        description="GPU rain effect",
        requires_core=">=0.1.0,<1.0",
    )
    clip_types = []
"""


def _write_plugin(base: Path, dir_name: str, toml: str, init: str) -> Path:
    plugin_dir = base / dir_name
    src = plugin_dir / "src" / dir_name.replace("-", "_")
    src.mkdir(parents=True)
    (plugin_dir / "pyproject.toml").write_text(toml)
    (src / "__init__.py").write_text(init)
    return plugin_dir


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_empty_plugins_dir(tmp_path):
    discovered, failed = discover_plugins(tmp_path)
    assert discovered == []
    assert failed == []


def test_missing_plugins_dir(tmp_path):
    discovered, failed = discover_plugins(tmp_path / "nonexistent")
    assert discovered == []
    assert failed == []


def test_discover_valid_plugin(tmp_path):
    _write_plugin(tmp_path, "acme-rain", GOOD_PLUGIN_TOML, GOOD_PLUGIN_INIT)

    discovered, failed = discover_plugins(tmp_path)

    assert len(discovered) == 1
    assert len(failed) == 0
    p = discovered[0]
    assert p.package_name == "acme-rain"
    assert p.version == "1.2.3"
    assert p.author == "jane@acme.com"


def test_discover_bad_toml(tmp_path):
    plugin_dir = tmp_path / "bad-toml"
    plugin_dir.mkdir()
    (plugin_dir / "pyproject.toml").write_text("not valid toml ][")

    discovered, failed = discover_plugins(tmp_path)

    assert len(discovered) == 0
    assert len(failed) == 1
    assert "bad pyproject.toml" in failed[0].error


def test_discover_missing_plugin_class(tmp_path):
    plugin_dir = tmp_path / "no-class"
    src = plugin_dir / "src" / "no_class"
    src.mkdir(parents=True)
    (plugin_dir / "pyproject.toml").write_text("[project]\nname = 'no-class'\nversion = '0.1.0'\n")
    (src / "__init__.py").write_text("# no Plugin class here\n")

    discovered, failed = discover_plugins(tmp_path)

    assert len(discovered) == 0
    assert len(failed) == 1
    assert failed[0].package_name == "no-class"


def test_discover_mixed(tmp_path):
    _write_plugin(tmp_path, "acme-rain", GOOD_PLUGIN_TOML, GOOD_PLUGIN_INIT)

    bad_dir = tmp_path / "bad-plugin"
    bad_dir.mkdir()
    (bad_dir / "pyproject.toml").write_text("[project]\nname = 'bad-plugin'\nversion = '0.1.0'\n")

    discovered, failed = discover_plugins(tmp_path)

    assert len(discovered) == 1
    assert len(failed) == 1


def test_discovered_plugin_manifest(tmp_path):
    _write_plugin(tmp_path, "acme-rain", GOOD_PLUGIN_TOML, GOOD_PLUGIN_INIT)
    discovered, _ = discover_plugins(tmp_path)

    assert discovered[0].manifest is not None
    assert discovered[0].manifest.display_name == "Acme Rain"


def test_discovered_plugin_no_manifest_on_non_protocol():
    class _BadPlugin:
        pass

    p = DiscoveredPlugin(
        package_name="bad",
        version="0.0.1",
        author=None,
        plugin_class=_BadPlugin,
        plugin_package_dir=Path("."),
    )
    assert p.manifest is None


def test_discover_std_plugin():
    """Smoke test: the real std plugin is discoverable from the repo plugins/ dir."""
    repo_plugins = Path(__file__).parent.parent.parent / "plugins"
    discovered, failed = discover_plugins(repo_plugins)

    names = [d.package_name for d in discovered]
    assert "pixfabrica-std" in names
    assert "pixfabrica-std-effects" in names
    assert failed == []
