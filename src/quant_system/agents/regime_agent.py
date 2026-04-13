"""Market regime detection for the modular monolith agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev

from quant_system.common.models import Bar


@dataclass(frozen=True, slots=True)
class RegimeState:
    regime: str
    confidence: float
    weights: dict[str, float]
    reason: str


@dataclass(frozen=True, slots=True)
class RegimeConfig:
    trend_threshold: float = 0.03
    low_vol_threshold: float = 0.20
    trend_vol_threshold: float = 0.25
    crisis_vol_threshold: float = 0.30
    crisis_corr_threshold: float = 0.70


class RegimeAgent:
    def __init__(self, config: RegimeConfig | None = None) -> None:
        self.config = config or RegimeConfig()

    def detect(self, history: dict[str, list[Bar]]) -> RegimeState:
        returns_by_symbol = {symbol: _returns(bars) for symbol, bars in history.items() if len(bars) >= 3}
        flat_returns = [value for values in returns_by_symbol.values() for value in values]
        if len(flat_returns) < 5:
            return RegimeState("uncertain", 0.30, _weights(0.33, 0.33, 0.34), "insufficient history")

        avg_daily_return = mean(flat_returns)
        annualized_vol = pstdev(flat_returns) * sqrt(252) if len(flat_returns) > 1 else 0.0
        trend_strength = avg_daily_return * 252
        corr = _average_pairwise_correlation(returns_by_symbol)

        if annualized_vol > self.config.crisis_vol_threshold and corr > self.config.crisis_corr_threshold:
            return RegimeState(
                "crisis",
                0.80,
                _weights(0.10, 0.10, 0.80),
                f"vol={annualized_vol:.4f}, corr={corr:.4f}",
            )
        if trend_strength > self.config.trend_threshold and annualized_vol < self.config.trend_vol_threshold:
            return RegimeState(
                "trending",
                0.70,
                _weights(0.70, 0.20, 0.10),
                f"trend={trend_strength:.4f}, vol={annualized_vol:.4f}",
            )
        if abs(trend_strength) <= self.config.trend_threshold and annualized_vol < self.config.low_vol_threshold:
            return RegimeState(
                "mean_reverting",
                0.60,
                _weights(0.20, 0.70, 0.10),
                f"trend={trend_strength:.4f}, vol={annualized_vol:.4f}",
            )
        return RegimeState(
            "uncertain",
            0.30,
            _weights(0.33, 0.33, 0.34),
            f"trend={trend_strength:.4f}, vol={annualized_vol:.4f}, corr={corr:.4f}",
        )


def _weights(momentum: float, mean_revert: float, defensive: float) -> dict[str, float]:
    return {
        "etf_momentum": momentum,
        "main_board_breakout": mean_revert,
        "defensive": defensive,
        "default": min(momentum, mean_revert),
    }


def _returns(bars: list[Bar]) -> list[float]:
    values: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        if previous.close > 0:
            values.append(current.close / previous.close - 1.0)
    return values


def _average_pairwise_correlation(returns_by_symbol: dict[str, list[float]]) -> float:
    series = [values for values in returns_by_symbol.values() if len(values) >= 2]
    if len(series) < 2:
        return 0.0
    correlations: list[float] = []
    for left_idx, left in enumerate(series):
        for right in series[left_idx + 1 :]:
            size = min(len(left), len(right))
            corr = _correlation(left[-size:], right[-size:])
            if corr is not None:
                correlations.append(corr)
    return mean(correlations) if correlations else 0.0


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_var = sum((x - left_mean) ** 2 for x in left)
    right_var = sum((y - right_mean) ** 2 for y in right)
    denominator = (left_var * right_var) ** 0.5
    if denominator == 0:
        return 0.0
    return numerator / denominator
