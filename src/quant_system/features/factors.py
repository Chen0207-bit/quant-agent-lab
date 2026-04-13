"""Simple low-frequency factors for MVP strategies."""

from __future__ import annotations

from math import sqrt
from statistics import pstdev
from typing import Sequence

from quant_system.common.models import Bar, Side
from quant_system.data.a_share_rules import would_cross_price_limit


def momentum(bars: list[Bar], lookback_days: int) -> float | None:
    if len(bars) <= lookback_days or lookback_days <= 0:
        return None
    start = bars[-lookback_days - 1].close
    end = bars[-1].close
    if start <= 0:
        return None
    return end / start - 1.0


def weighted_momentum(
    bars: list[Bar],
    lookback_windows: Sequence[int],
    window_weights: Sequence[float],
) -> float | None:
    windows = tuple(int(window) for window in lookback_windows if int(window) > 0)
    if not windows:
        return None
    weights = _normalized_weights(window_weights, len(windows))
    values: list[float] = []
    for window in windows:
        value = momentum(bars, window)
        if value is None:
            return None
        values.append(value)
    return sum(value * weight for value, weight in zip(values, weights))


def annualized_volatility(bars: list[Bar], lookback_days: int) -> float | None:
    if len(bars) <= lookback_days or lookback_days <= 1:
        return None
    returns = _returns(bars[-lookback_days - 1 :])
    if len(returns) < 2:
        return None
    return pstdev(returns) * sqrt(252)


def average_true_range(bars: list[Bar], lookback_days: int) -> float | None:
    if len(bars) <= lookback_days or lookback_days <= 0:
        return None
    window = bars[-lookback_days - 1 :]
    prev_close = window[0].close
    true_ranges: list[float] = []
    for bar in window[1:]:
        tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
        if prev_close <= 0:
            return None
        true_ranges.append(tr / prev_close)
        prev_close = bar.close
    if not true_ranges:
        return None
    return sum(true_ranges) / len(true_ranges)


def moving_average(bars: list[Bar], lookback_days: int) -> float | None:
    if len(bars) < lookback_days or lookback_days <= 0:
        return None
    return sum(bar.close for bar in bars[-lookback_days:]) / lookback_days


def breakout_score(bars: list[Bar], lookback_days: int) -> float | None:
    if len(bars) <= lookback_days or lookback_days <= 0:
        return None
    previous_high = max(bar.high for bar in bars[-lookback_days - 1 : -1])
    if previous_high <= 0:
        return None
    return bars[-1].close / previous_high - 1.0


def traded_amount(bar: Bar) -> float:
    if bar.amount > 0:
        return bar.amount
    return bar.volume * bar.close


def is_limit_up_buy_blocked(bar: Bar) -> bool:
    return would_cross_price_limit(Side.BUY, bar.close, bar.limit_up, bar.limit_down)


def _returns(bars: list[Bar]) -> list[float]:
    values: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        if previous.close > 0:
            values.append(current.close / previous.close - 1.0)
    return values


def _normalized_weights(weights: Sequence[float], size: int) -> tuple[float, ...]:
    raw = tuple(float(weight) for weight in weights)
    if len(raw) != size or sum(raw) <= 0:
        return tuple(1.0 / size for _ in range(size))
    total = sum(raw)
    return tuple(weight / total for weight in raw)
