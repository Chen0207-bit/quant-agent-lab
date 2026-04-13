"""Historical bar buffers."""

from __future__ import annotations

from quant_system.common.models import Bar


def append_daily_bars(history: dict[str, list[Bar]], bars: dict[str, Bar]) -> None:
    for symbol, bar in bars.items():
        history.setdefault(symbol, []).append(bar)
