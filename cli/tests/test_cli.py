from typer.testing import CliRunner

from pixfabrica_cli.main import app

runner = CliRunner()


def test_render_missing_graph():
    result = runner.invoke(app, ["render", "nonexistent.json"])
    assert result.exit_code != 0


def test_render_help():
    result = runner.invoke(app, ["render", "--help"])
    assert result.exit_code == 0
    assert "graph" in result.output.lower()


def test_bake_preview_sample_help():
    result = runner.invoke(app, ["web", "bake-preview-sample", "--help"])
    assert result.exit_code == 0
    assert "analyzer" in result.output.lower()


def test_bake_preview_samples_help():
    result = runner.invoke(app, ["web", "bake-preview-samples", "--help"])
    assert result.exit_code == 0
    assert "sources" in result.output.lower()
