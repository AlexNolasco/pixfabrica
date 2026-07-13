from __future__ import annotations


def hash_string(s: str) -> int:
    """Deterministic string → seed (polynomial hash, matches TS hashStringToSeed)."""
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) % 2147483647
    return h or 1


class SeededRandom:
    """Park-Miller LCG — matches the TypeScript SeededRandom implementation exactly."""

    def __init__(self, seed: int) -> None:
        self._state = seed % 2147483647 or 1

    @classmethod
    def from_string(cls, s: str) -> SeededRandom:
        return cls(hash_string(s))

    def next(self) -> float:
        """Float in [0, 1)."""
        self._state = (self._state * 16807) % 2147483647
        return (self._state - 1) / 2147483646

    def next_int(self, min_val: int, max_val: int) -> int:
        """Integer in [min_val, max_val] inclusive."""
        return int(self.next() * (max_val - min_val + 1)) + min_val
