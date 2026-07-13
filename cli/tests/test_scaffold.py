import pytest

from pixfabrica_cli.scaffold import scaffold_plugin, slug_to_display, slug_to_package


def test_slug_to_package():
    assert slug_to_package("acme-rain") == "acme_rain"
    assert slug_to_package("my cool plugin") == "my_cool_plugin"
    assert slug_to_package("already_fine") == "already_fine"
    assert slug_to_package("pixfabrica-std-sample") == "pixfabrica_std_sample"


def test_slug_to_display():
    assert slug_to_display("acme-rain") == "Acme Rain"
    assert slug_to_display("my_plugin") == "My Plugin"
    assert slug_to_display("pixfabrica-std-sample") == "Pixfabrica Std Sample"


def test_scaffold_creates_structure(tmp_path):
    plugin_dir = scaffold_plugin("acme-rain", tmp_path)

    assert plugin_dir == tmp_path / "acme-rain"
    assert (plugin_dir / "pyproject.toml").exists()
    assert (plugin_dir / "README.md").exists()
    assert (plugin_dir / ".gitignore").exists()
    assert (plugin_dir / "src" / "acme_rain" / "__init__.py").exists()
    assert (plugin_dir / "src" / "acme_rain" / "icons.py").exists()
    assert (plugin_dir / "src" / "acme_rain" / "placeholder.py").exists()


def test_scaffold_pyproject_content(tmp_path):
    scaffold_plugin("acme-rain", tmp_path)
    content = (tmp_path / "acme-rain" / "pyproject.toml").read_text()

    assert 'name = "acme-rain"' in content
    assert "pixfabrica-core" in content
    assert 'path = "../../core"' in content
    assert "skia-python" in content
    assert '"pixfabrica.nodes"' not in content


def test_scaffold_init_content(tmp_path):
    scaffold_plugin("acme-rain", tmp_path)
    content = (tmp_path / "acme-rain" / "src" / "acme_rain" / "__init__.py").read_text()

    assert "PluginManifest" in content
    assert '"acme-rain"' in content
    assert '"Acme Rain"' in content
    assert "import icons" in content
    assert "PlaceholderRect" in content
    assert "clip_types" in content
    assert "nodes = clip_types" not in content


def test_scaffold_placeholder_uses_clip_type(tmp_path):
    scaffold_plugin("acme-rain", tmp_path)
    content = (tmp_path / "acme-rain" / "src" / "acme_rain" / "placeholder.py").read_text()
    assert 'clip_type: ClassVar[str] = "acme-rain-placeholder"' in content
    assert "ClipSkia" in content
    assert "pixfabrica_core.clips" in content


def test_scaffold_readme_install_path(tmp_path):
    scaffold_plugin("pixfabrica-std-sample", tmp_path)
    content = (tmp_path / "pixfabrica-std-sample" / "README.md").read_text()

    assert "plugins/pixfabrica-std-sample" in content
    assert "uv add --editable" in content
    assert "--no-workspace" in content
    assert "../../core" in content


def test_scaffold_raises_if_exists(tmp_path):
    scaffold_plugin("acme-rain", tmp_path)
    with pytest.raises(FileExistsError):
        scaffold_plugin("acme-rain", tmp_path)
