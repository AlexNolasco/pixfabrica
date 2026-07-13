"""Deterministic 2D simplex noise (Seriously.js camerashake port)."""

from __future__ import annotations

import math

from pixfabrica_core.random import SeededRandom

_F2 = 0.5 * (math.sqrt(3.0) - 1.0)
_G2 = (3.0 - math.sqrt(3.0)) / 6.0

_GRAD3 = (
    1.0,
    1.0,
    0.0,
    -1.0,
    1.0,
    0.0,
    1.0,
    -1.0,
    0.0,
    -1.0,
    -1.0,
    0.0,
    1.0,
    0.0,
    1.0,
    -1.0,
    0.0,
    1.0,
    1.0,
    0.0,
    -1.0,
    -1.0,
    0.0,
    -1.0,
    0.0,
    1.0,
    1.0,
    0.0,
    -1.0,
    1.0,
    0.0,
    -1.0,
    -1.0,
    0.0,
    1.0,
    -1.0,
)


class Simplex2D:
    """Seeded 2D simplex noise; permutation table built once at construction."""

    def __init__(self, rng: SeededRandom) -> None:
        p = [int(rng.next() * 256.0) & 255 for _ in range(256)]
        perm = [p[i & 255] for i in range(512)]
        self._perm_mod12 = [perm[i] % 12 for i in range(512)]
        self._perm = perm

    def noise2d(self, xin: float, yin: float) -> float:
        n0 = 0.0
        n1 = 0.0
        n2 = 0.0

        s = (xin + yin) * _F2
        i = math.floor(xin + s)
        j = math.floor(yin + s)
        t = (i + j) * _G2

        xx0 = i - t
        yy0 = j - t

        x0 = xin - xx0
        y0 = yin - yy0

        i1 = 1 if x0 > y0 else 0
        j1 = 0 if i1 else 1

        x1 = x0 - i1 + _G2
        y1 = y0 - j1 + _G2
        x2 = x0 - 1.0 + 2.0 * _G2
        y2 = y0 - 1.0 + 2.0 * _G2

        ii = int(i) & 255
        jj = int(j) & 255

        t0 = 0.5 - x0 * x0 - y0 * y0
        if t0 >= 0.0:
            gi = self._perm_mod12[ii + self._perm[jj]] * 3
            t0 *= t0
            n0 = t0 * t0 * (_GRAD3[gi] * x0 + _GRAD3[gi + 1] * y0)

        t1 = 0.5 - x1 * x1 - y1 * y1
        if t1 >= 0.0:
            gi = self._perm_mod12[ii + i1 + self._perm[jj + j1]] * 3
            t1 *= t1
            n1 = t1 * t1 * (_GRAD3[gi] * x1 + _GRAD3[gi + 1] * y1)

        t2 = 0.5 - x2 * x2 - y2 * y2
        if t2 >= 0.0:
            gi = self._perm_mod12[ii + 1 + self._perm[jj + 1]] * 3
            t2 *= t2
            n2 = t2 * t2 * (_GRAD3[gi] * x2 + _GRAD3[gi + 1] * y2)

        return 70.0 * (n0 + n1 + n2)
