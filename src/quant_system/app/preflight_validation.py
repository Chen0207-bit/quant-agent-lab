"""Preflight validation helpers for daily report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import mean
from typing import Mapping, Sequence

from quant_system.agents.regime_agent import RegimeAgent
from quant_system.agents.signal_agent import SignalAgent
from quant_system.backtest.history import append_daily_bars
from quant_system.common.models import Bar, Instrument, PortfolioConstraints, PositionSnapshot
from quant_system.config.settings import UniverseConfig
from quant_system.data.universe import build_universe_snapshot
from quant_system.strategies.base import Strategy


@dataclass(slots=True)
class _MetricAccumulator:
    horizons: tuple[int, ...]
    sample_days: int = 0
    selected_observations: int = 0
    rejected_observations: int = 0
    selected_returns: dict[int, list[float]] = field(init=False)
    rejected_returns: dict[int, list[float]] = field(init=False)
    spreads: dict[int, list[float]] = field(init=False)
    hit_counts: dict[int, int] = field(init=False)
    primary_curve_returns: list[float] = field(init=False)

    def __post_init__(self) -> None:
        self.selected_returns = {h: [] for h in self.horizons}
        self.rejected_returns = {h: [] for h in self.horizons}
        self.spreads = {h: [] for h in self.horizons}
        self.hit_counts = {h: 0 for h in self.horizons}
        self.primary_curve_returns = []

    def add_day(
        self,
        *,
        selected_symbols: Sequence[str],
        rejected_symbols: Sequence[str],
        current_index: int,
        dates: Sequence[date],
        bars_by_date: Mapping[date, Mapping[str, Bar]],
        primary_horizon: int,
    ) -> None:
        self.sample_days += 1
        self.selected_observations += len(selected_symbols)
        self.rejected_observations += len(rejected_symbols)
        primary_return: float | None = None
        for horizon in self.horizons:
            selected_value = _mean_forward_return(selected_symbols, current_index, horizon, dates, bars_by_date)
            rejected_value = _mean_forward_return(rejected_symbols, current_index, horizon, dates, bars_by_date)
            if selected_value is not None:
                self.selected_returns[horizon].append(selected_value)
                if selected_value > 0:
                    self.hit_counts[horizon] += 1
                if horizon == primary_horizon:
                    primary_return = selected_value
            if rejected_value is not None:
                self.rejected_returns[horizon].append(rejected_value)
            if selected_value is not None and rejected_value is not None:
                self.spreads[horizon].append(selected_value - rejected_value)
        self.primary_curve_returns.append(primary_return or 0.0)

    def summarize(self, *, family: str | None = None, strategy_id: str | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "sample_days": self.sample_days,
            "selected_observations": self.selected_observations,
            "rejected_observations": self.rejected_observations,
            "max_drawdown": _max_drawdown(self.primary_curve_returns),
            "horizons": {
                str(horizon): {
                    "selected_avg_return": _avg(self.selected_returns[horizon]),
                    "rejected_avg_return": _avg(self.rejected_returns[horizon]),
                    "spread": _avg(self.spreads[horizon]),
                    "hit_rate": _ratio(self.hit_counts[horizon], len(self.selected_returns[horizon])),
                    "observations": len(self.selected_returns[horizon]),
                }
                for horizon in self.horizons
            },
        }
        if family is not None:
            payload["family"] = family
        if strategy_id is not None:
            payload["strategy_id"] = strategy_id
        return payload


def run_preflight_validation(
    *,
    as_of: date,
    bars_by_date: Mapping[date, Mapping[str, Bar]],
    strategies: Sequence[Strategy],
    instruments: Mapping[str, Instrument],
    regime_agent: RegimeAgent,
    portfolio_constraints: PortfolioConstraints,
    universe_config: UniverseConfig | None = None,
    trailing_window_days: int = 252,
    forward_return_horizons: Sequence[int] = (1, 5, 20),
    initial_cash: float = 100000.0,
) -> dict[str, object]:
    horizons = tuple(sorted({int(h) for h in forward_return_horizons if int(h) > 0}))
    if not horizons:
        raise ValueError("forward_return_horizons must not be empty")
    dates = sorted(bars_by_date)
    if as_of not in dates:
        raise ValueError(f"as_of {as_of.isoformat()} not found in bars_by_date")

    as_of_index = dates.index(as_of)
    sample_end_index = as_of_index - max(horizons)
    if sample_end_index < 0:
        return _empty_validation_payload(as_of, horizons, ["no complete forward-return window before as_of"])

    sample_start_index = max(0, sample_end_index - max(trailing_window_days, 1) + 1)
    primary_horizon = _primary_horizon(horizons)
    signal_agent = SignalAgent(strategies)
    overall = _MetricAccumulator(horizons)
    strategy_accumulators: dict[str, tuple[str, _MetricAccumulator]] = {}
    history: dict[str, list[Bar]] = {}

    for current_index, trade_date in enumerate(dates[: as_of_index + 1]):
        bars = dict(bars_by_date[trade_date])
        append_daily_bars(history, bars)
        if current_index < sample_start_index or current_index > sample_end_index:
            continue

        snapshot = PositionSnapshot(trade_date, initial_cash, {})
        regime = regime_agent.detect(history)
        universe_snapshot = build_universe_snapshot(trade_date, instruments, bars, universe_config)
        plan = signal_agent.generate_signal_plan(
            as_of=trade_date,
            history=history,
            portfolio=snapshot,
            regime=regime,
            universe_snapshot=universe_snapshot,
            portfolio_constraints=portfolio_constraints,
        )

        selected_symbols = sorted({target.symbol for target in plan.targets})
        rejected_symbols = sorted(
            {record.symbol for record in plan.diagnostics if record.rejection_reason and record.symbol}
        )
        overall.add_day(
            selected_symbols=selected_symbols,
            rejected_symbols=rejected_symbols,
            current_index=current_index,
            dates=dates,
            bars_by_date=bars_by_date,
            primary_horizon=primary_horizon,
        )

        per_strategy: dict[str, dict[str, object]] = {}
        for record in plan.diagnostics:
            bucket = per_strategy.setdefault(
                record.strategy_id,
                {"family": record.family, "selected": set(), "rejected": set()},
            )
            if record.selected:
                bucket["selected"].add(record.symbol)
            if record.rejection_reason:
                bucket["rejected"].add(record.symbol)

        for strategy_id, bucket in per_strategy.items():
            family = str(bucket["family"])
            _, accumulator = strategy_accumulators.setdefault(strategy_id, (family, _MetricAccumulator(horizons)))
            accumulator.add_day(
                selected_symbols=sorted(bucket["selected"]),
                rejected_symbols=sorted(bucket["rejected"]),
                current_index=current_index,
                dates=dates,
                bars_by_date=bars_by_date,
                primary_horizon=primary_horizon,
            )

    payload = overall.summarize()
    payload.update(
        {
            "as_of": as_of.isoformat(),
            "validation_window_start": dates[sample_start_index].isoformat(),
            "validation_window_end": dates[sample_end_index].isoformat(),
            "forward_return_horizons": list(horizons),
            "selected_vs_rejected_spread": payload.pop("horizons"),
            "strategy_metrics": [
                accumulator.summarize(family=family, strategy_id=strategy_id)
                for strategy_id, (family, accumulator) in sorted(strategy_accumulators.items())
            ],
        }
    )
    warnings = _validation_warnings(payload, primary_horizon)
    payload["warnings"] = warnings
    payload["validation_status"] = _validation_status(payload, warnings)
    return payload


def render_preflight_validation_summary(payload: Mapping[str, object]) -> str:
    lines = [
        "## Preflight Validation",
        "",
        f"- Status: {payload.get('validation_status', 'missing')}",
        f"- Window: {payload.get('validation_window_start', 'n/a')} -> {payload.get('validation_window_end', 'n/a')}",
        f"- Sample days: {int(payload.get('sample_days', 0) or 0)}",
        f"- Primary spread ({_primary_horizon(tuple(int(x) for x in payload.get('forward_return_horizons', [1]) or [1]))}d): {_format_primary_spread(payload)}",
        f"- Max drawdown: {_format_pct(payload.get('max_drawdown'))}",
    ]
    warnings = [str(item) for item in payload.get('warnings', []) if str(item)]
    if warnings:
        lines.append("- Warnings: " + "; ".join(warnings))
    return "\n".join(lines)


def render_preflight_validation_markdown(payload: Mapping[str, object]) -> str:
    lines = [f"# Preflight Validation: {payload.get('as_of', '')}", "", render_preflight_validation_summary(payload)]
    strategy_metrics = payload.get("strategy_metrics", [])
    if isinstance(strategy_metrics, list) and strategy_metrics:
        lines.extend(["", "## Strategy Metrics"])
        for item in strategy_metrics:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('strategy_id', 'unknown')} ({item.get('family', 'unknown')}): "
                f"sample_days={int(item.get('sample_days', 0) or 0)}, "
                f"selected_obs={int(item.get('selected_observations', 0) or 0)}, "
                f"rejected_obs={int(item.get('rejected_observations', 0) or 0)}, "
                f"max_drawdown={_format_pct(item.get('max_drawdown'))}"
            )
    return "\n".join(lines).rstrip() + "\n"


def _empty_validation_payload(as_of: date, horizons: Sequence[int], warnings: list[str]) -> dict[str, object]:
    return {
        "as_of": as_of.isoformat(),
        "validation_window_start": None,
        "validation_window_end": None,
        "sample_days": 0,
        "max_drawdown": None,
        "forward_return_horizons": list(horizons),
        "selected_vs_rejected_spread": {
            str(horizon): {
                "selected_avg_return": None,
                "rejected_avg_return": None,
                "spread": None,
                "hit_rate": None,
                "observations": 0,
            }
            for horizon in horizons
        },
        "strategy_metrics": [],
        "warnings": warnings,
        "validation_status": "insufficient_data",
    }


def _mean_forward_return(
    symbols: Sequence[str],
    current_index: int,
    horizon: int,
    dates: Sequence[date],
    bars_by_date: Mapping[date, Mapping[str, Bar]],
) -> float | None:
    values: list[float] = []
    if not symbols:
        return None
    future_index = current_index + horizon
    if future_index >= len(dates):
        return None
    current_date = dates[current_index]
    future_date = dates[future_index]
    for symbol in symbols:
        left = bars_by_date.get(current_date, {}).get(symbol)
        right = bars_by_date.get(future_date, {}).get(symbol)
        if left is None or right is None or left.close <= 0:
            continue
        values.append(right.close / left.close - 1.0)
    return _avg(values)


def _avg(values: Sequence[float]) -> float | None:
    return mean(values) if values else None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _primary_horizon(horizons: Sequence[int]) -> int:
    for candidate in (5, 1):
        if candidate in horizons:
            return candidate
    return int(horizons[0])


def _validation_warnings(payload: Mapping[str, object], primary_horizon: int) -> list[str]:
    warnings: list[str] = []
    sample_days = int(payload.get("sample_days", 0) or 0)
    if sample_days < 20:
        warnings.append("sample window shorter than 20 trading days")
    spread_payload = payload.get("selected_vs_rejected_spread", {})
    if isinstance(spread_payload, dict):
        horizon_payload = spread_payload.get(str(primary_horizon), {})
        if isinstance(horizon_payload, dict):
            spread = horizon_payload.get("spread")
            selected_avg = horizon_payload.get("selected_avg_return")
            if selected_avg is None:
                warnings.append("no selected forward-return observations at primary horizon")
            elif float(selected_avg) <= 0:
                warnings.append("selected basket forward return is non-positive at primary horizon")
            if spread is None:
                warnings.append("selected-vs-rejected spread unavailable at primary horizon")
            elif float(spread) <= 0:
                warnings.append("selected basket did not outperform rejected basket at primary horizon")
    max_drawdown = payload.get("max_drawdown")
    if isinstance(max_drawdown, (int, float)) and float(max_drawdown) < -0.10:
        warnings.append("selected basket max drawdown worse than -10% in validation window")
    return warnings


def _validation_status(payload: Mapping[str, object], warnings: Sequence[str]) -> str:
    if int(payload.get("sample_days", 0) or 0) < 20:
        return "insufficient_data"
    return "warn" if warnings else "pass"


def _max_drawdown(returns: Sequence[float]) -> float | None:
    if not returns:
        return None
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for daily_return in returns:
        equity *= 1.0 + float(daily_return)
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def _format_primary_spread(payload: Mapping[str, object]) -> str:
    horizons = tuple(int(x) for x in payload.get("forward_return_horizons", [1]) or [1])
    primary_horizon = _primary_horizon(horizons)
    spread_payload = payload.get("selected_vs_rejected_spread", {})
    if not isinstance(spread_payload, dict):
        return "n/a"
    metric = spread_payload.get(str(primary_horizon), {})
    if not isinstance(metric, dict):
        return "n/a"
    spread = metric.get("spread")
    return _format_pct(spread)


def _format_pct(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2%}"
    return "n/a"
