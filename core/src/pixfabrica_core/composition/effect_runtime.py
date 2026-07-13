"""Process-wide singleton holders for VRAM-heavy effect plugins."""

from __future__ import annotations

import threading
from typing import Any


class EffectSingleton[T]:
    """Thread-safe lazy slot populated during ``prepare()``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: T | None = None

    def get_or_create(self, factory: Any) -> T:
        if self._value is not None:
            return self._value
        with self._lock:
            if self._value is None:
                self._value = factory()
            value = self._value
            assert value is not None
            return value

    def clear(self) -> None:
        with self._lock:
            self._value = None


class EffectRuntimeRegistry:
    """One registry per worker process — keyed by effect ``effect_type``."""

    def __init__(self) -> None:
        self._singletons: dict[str, EffectSingleton[Any]] = {}

    def singleton(self, effect_type: str) -> EffectSingleton[Any]:
        if effect_type not in self._singletons:
            self._singletons[effect_type] = EffectSingleton()
        return self._singletons[effect_type]

    def clear(self) -> None:
        self._singletons.clear()
