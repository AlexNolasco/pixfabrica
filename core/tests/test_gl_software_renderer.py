"""Software GL_RENDERER detection."""

from pixfabrica_core.capabilities.gl import is_software_gl_renderer


def test_llvmpipe_is_software() -> None:
    assert is_software_gl_renderer("llvmpipe (LLVM 15.0.6, 256 bits)")


def test_swiftshader_is_software() -> None:
    assert is_software_gl_renderer("Google SwiftShader")


def test_nvidia_is_not_software() -> None:
    assert not is_software_gl_renderer("NVIDIA GeForce RTX 5090/PCIe/SSE2")


def test_radeon_is_not_software() -> None:
    assert not is_software_gl_renderer("AMD Radeon RX 7900 XT (radeonsi, navi31, LLVM 15.0.6)")


def test_empty_renderer_is_not_software() -> None:
    assert not is_software_gl_renderer(None)
    assert not is_software_gl_renderer("")
