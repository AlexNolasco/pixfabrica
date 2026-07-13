from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from pixfabrica_cli.main import app
from pixfabrica_core.plugins import PluginManifest
from pixfabrica_core.plugins.discovery import DiscoveredPlugin, FailedPlugin

runner = CliRunner()


class _FakeClip:
    clip_type = "acme-rain"


class _FakePlugin:
    manifest = PluginManifest(
        name="acme-rain",
        display_name="Acme Rain",
        description="GPU rain effect",
        requires_core=">=0.1.0,<1.0",
    )
    clip_types = [_FakeClip]


_DISCOVERED = [
    DiscoveredPlugin(
        package_name="acme-rain",
        version="1.2.3",
        author="Jane Dev",
        plugin_class=_FakePlugin,
        plugin_package_dir=Path("."),
    )
]


def test_list_no_plugins():
    with patch("pixfabrica_cli.commands.plugin.discover_plugins", return_value=([], [])):
        result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "No plugins installed" in result.output


def test_list_shows_installed_plugin():
    with patch("pixfabrica_cli.commands.plugin.discover_plugins", return_value=(_DISCOVERED, [])):
        result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "Acme Rain" in result.output
    assert "1.2.3" in result.output
    assert "Jane Dev" in result.output


def test_list_shows_failed_plugin():
    failed = [
        FailedPlugin(
            package_name="bad-plugin", plugin_dir="plugins/bad-plugin", error="ImportError"
        )
    ]
    with patch("pixfabrica_cli.commands.plugin.discover_plugins", return_value=([], failed)):
        result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "Failed to load" in result.output
    assert "bad-plugin" in result.output


def test_list_clip_types_column():
    with patch("pixfabrica_cli.commands.plugin.discover_plugins", return_value=(_DISCOVERED, [])):
        result = runner.invoke(app, ["plugin", "list", "--clip-types"])
    assert result.exit_code == 0
    assert "Clip types" in result.output
    assert "acme-rain" in result.output
