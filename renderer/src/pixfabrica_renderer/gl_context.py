from __future__ import annotations

from contextlib import suppress

import moderngl
import numpy as np
import skia

from pixfabrica_renderer.gl_probe import create_standalone_gl_context


class GLContext:
    """Owns a moderngl standalone context and one FBO for offscreen rendering."""

    def __init__(self, width: int, height: int) -> None:
        self._ctx = create_standalone_gl_context()
        self._ctx.enable(moderngl.BLEND)
        # Premultiplied-alpha compositing: shaders output vec4(rgb * a, a).
        self._ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
        # Color + depth so 3D mesh clips can use DEPTH_TEST; 2D GL clips leave depth
        # disabled and are unaffected (same as drawing to a color-only FBO).
        self._color_tex = self._ctx.texture((width, height), 4)
        self._depth_rb = self._ctx.depth_renderbuffer((width, height))
        self._fbo = self._ctx.framebuffer(
            color_attachments=[self._color_tex],
            depth_attachment=self._depth_rb,
        )
        # Scratch target for per-clip GL effect ping-pong at full job size.
        self._ping_tex = self._ctx.texture((width, height), 4)
        self._ping_fbo = self._ctx.framebuffer(color_attachments=[self._ping_tex])
        self._width = width
        self._height = height
        self._pixel_buf: bytes = b""
        self._released = False

    def release(self) -> None:
        """Idempotent teardown — worker processes call this before exit."""
        if self._released:
            return
        self._released = True
        with suppress(Exception):
            self._ping_fbo.release()
        with suppress(Exception):
            self._ping_tex.release()
        with suppress(Exception):
            self._fbo.release()
        with suppress(Exception):
            self._color_tex.release()
        with suppress(Exception):
            self._depth_rb.release()
        with suppress(Exception):
            self._ctx.release()

    @property
    def ctx(self) -> moderngl.Context:
        return self._ctx

    @property
    def fbo(self) -> moderngl.Framebuffer:
        return self._fbo

    def clear(self) -> None:
        self._fbo.use()
        self._ctx.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)

    def reset_clip_state(self) -> None:
        """Restore full-canvas viewport and disable scissor on the shared FBO.

        Plugins may leak clip state from draw(); clips assume a full-canvas
        viewport, so the compositor resets it rather than trusting plugins.
        """
        full = (0, 0, self._width, self._height)
        self._fbo.viewport = full
        self._fbo.scissor = full

    def upload_skia_surface(self, surface: skia.Surface) -> moderngl.Texture:
        """Snapshot the Skia surface and upload it as a GL texture for post-processing."""
        surface.getCanvas().flush()
        image = surface.makeImageSnapshot()
        row_bytes = self._width * 4
        buf = bytearray(self._height * row_bytes)
        image.readPixels(skia.ImageInfo.MakeN32Premul(self._width, self._height), buf, row_bytes)
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(self._height, self._width, 4)
        arr = np.flipud(arr).copy()  # Skia top-left → GL bottom-left
        arr[:, :, [0, 2]] = arr[:, :, [2, 0]]  # BGRA → RGBA
        texture = self._ctx.texture((self._width, self._height), 4, arr.tobytes())
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        texture.repeat_x = False
        texture.repeat_y = False
        return texture

    def to_skia_bitmap(self) -> skia.Bitmap:
        """Read the GL FBO into a Skia bitmap for compositor ``drawBitmap``.

        Layout: BGRA, top-left origin (Y-flipped from GL's bottom-left).

        Alpha contract: shaders emit **premultiplied** ``vec4(rgb * a, a)`` and
        blending uses ``ONE, ONE_MINUS_SRC_ALPHA``, so FBO RGB is already premul.
        Skia ``N32Premul`` expects the same — swizzle only, no second multiply.
        """
        raw = np.frombuffer(self._fbo.read(components=4), dtype=np.uint8)
        arr = raw.reshape(self._height, self._width, 4)
        arr = np.flipud(arr).copy()  # GL bottom-left → top-left
        arr[:, :, [0, 2]] = arr[:, :, [2, 0]]  # RGBA → BGRA
        # installPixels holds a pointer, not a copy — keep bytes alive until drawBitmap.
        self._pixel_buf = arr.tobytes()
        bitmap = skia.Bitmap()
        bitmap.installPixels(
            skia.ImageInfo.MakeN32Premul(self._width, self._height),
            self._pixel_buf,
            self._width * 4,
        )
        return bitmap
