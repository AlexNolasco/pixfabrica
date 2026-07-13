"""GL probe treats software renderers as unavailable."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pixfabrica_renderer.gl_probe import probe_gl_available, reset_gl_probe_cache


def test_probe_rejects_llvmpipe(monkeypatch) -> None:
    monkeypatch.delenv("PIXFABRICA_GL_PROBE", raising=False)
    reset_gl_probe_cache()
    mock_ctx = MagicMock()
    mock_ctx.info = {"GL_RENDERER": "llvmpipe (LLVM 15.0.6, 256 bits)"}

    with patch(
        "pixfabrica_renderer.gl_probe.create_standalone_gl_context",
        return_value=mock_ctx,
    ):
        cap = probe_gl_available(force=True)

    assert cap.available is False
    assert cap.reason == "software_gl_renderer"
    assert "llvmpipe" in (cap.renderer or "")


def test_probe_accepts_gpu_renderer(monkeypatch) -> None:
    monkeypatch.delenv("PIXFABRICA_GL_PROBE", raising=False)
    reset_gl_probe_cache()
    mock_ctx = MagicMock()
    mock_ctx.info = {"GL_RENDERER": "NVIDIA GeForce RTX 5090/PCIe/SSE2"}

    with patch(
        "pixfabrica_renderer.gl_probe.create_standalone_gl_context",
        return_value=mock_ctx,
    ):
        cap = probe_gl_available(force=True)

    assert cap.available is True
    assert cap.renderer is not None
    assert "NVIDIA" in cap.renderer
