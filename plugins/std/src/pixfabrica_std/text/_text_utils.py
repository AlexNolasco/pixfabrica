from __future__ import annotations


def _case(s: str, mode: str) -> str:
    if mode == "upper":
        return s.upper()
    if mode == "lower":
        return s.lower()
    return s
