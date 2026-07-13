"""Provider registry: provenance blob → attribution string."""

from __future__ import annotations

from collections.abc import Callable

from pixfabrica_api.stock_attribution.models import StockProvenance
from pixfabrica_api.stock_attribution.providers import civitai, pexels

Formatter = Callable[[StockProvenance], str | None]

_FORMATTERS: dict[str, Formatter] = {
    "pexels": pexels.format_attribution,
    "civitai": civitai.format_attribution,
}


def format_stock_attribution(provenance: StockProvenance) -> tuple[str, str] | None:
    """Return ``(source_attribution, source_provider)`` or ``None`` if unsupported."""
    provider = provenance.provider.strip().lower()
    formatter = _FORMATTERS.get(provider)
    if formatter is None:
        return None
    text = formatter(provenance.model_copy(update={"provider": provider}))
    if not text:
        return None
    return text, provider
