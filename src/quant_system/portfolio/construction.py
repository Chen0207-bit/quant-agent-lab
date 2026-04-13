"""Constraint-aware portfolio construction helpers."""

from __future__ import annotations

from quant_system.common.models import PortfolioConstraints, PositionSnapshot, UniverseSnapshot


def apply_portfolio_constraints(
    target_weights: dict[str, float],
    portfolio: PositionSnapshot,
    universe_snapshot: UniverseSnapshot | None,
    constraints: PortfolioConstraints,
) -> tuple[dict[str, float], list[str]]:
    weights = {symbol: max(weight, 0.0) for symbol, weight in target_weights.items() if weight > 0}
    notes: list[str] = []
    weights = _apply_industry_cap(weights, universe_snapshot, constraints.max_industry_weight, notes)
    weights = _apply_single_name_cap(weights, constraints.max_position_weight, notes)
    weights = _apply_gross_cap(weights, max(0.0, 1.0 - constraints.min_cash_buffer_pct), notes)
    weights = _apply_turnover_budget(weights, portfolio, constraints.turnover_budget, notes)
    weights = _apply_single_name_cap(weights, constraints.max_position_weight, notes)
    return weights, notes


def _apply_single_name_cap(weights: dict[str, float], cap: float, notes: list[str]) -> dict[str, float]:
    if cap <= 0:
        return {}
    adjusted: dict[str, float] = {}
    for symbol, weight in weights.items():
        adjusted_weight = min(weight, cap)
        if adjusted_weight < weight:
            notes.append(f"single_name_cap:{symbol}:{weight:.4f}->{adjusted_weight:.4f}")
        adjusted[symbol] = adjusted_weight
    return adjusted


def _apply_industry_cap(
    weights: dict[str, float],
    universe_snapshot: UniverseSnapshot | None,
    cap: float,
    notes: list[str],
) -> dict[str, float]:
    if universe_snapshot is None or cap <= 0:
        return dict(weights)
    by_industry: dict[str, list[str]] = {}
    for symbol in weights:
        member = universe_snapshot.members.get(symbol)
        industry = member.industry if member is not None else "unknown"
        if not industry or industry == "unknown":
            continue
        by_industry.setdefault(industry, []).append(symbol)

    adjusted = dict(weights)
    for industry, symbols in by_industry.items():
        total = sum(adjusted[symbol] for symbol in symbols)
        if total <= cap or total <= 0:
            continue
        ratio = cap / total
        notes.append(f"industry_cap:{industry}:{total:.4f}->{cap:.4f}")
        for symbol in symbols:
            adjusted[symbol] *= ratio
    return adjusted


def _apply_gross_cap(weights: dict[str, float], cap: float, notes: list[str]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0 or total <= cap:
        return dict(weights)
    ratio = cap / total
    notes.append(f"gross_cap:{total:.4f}->{cap:.4f}")
    return {symbol: weight * ratio for symbol, weight in weights.items()}


def _apply_turnover_budget(
    weights: dict[str, float],
    portfolio: PositionSnapshot,
    budget: float,
    notes: list[str],
) -> dict[str, float]:
    if budget <= 0:
        return {}
    current = _current_weights(portfolio)
    symbols = set(weights) | set(current)
    turnover = sum(abs(weights.get(symbol, 0.0) - current.get(symbol, 0.0)) for symbol in symbols)
    if turnover <= budget or turnover <= 0:
        return dict(weights)
    ratio = budget / turnover
    adjusted: dict[str, float] = {}
    for symbol in symbols:
        base = current.get(symbol, 0.0)
        delta = weights.get(symbol, 0.0) - base
        candidate = base + delta * ratio
        if candidate > 0:
            adjusted[symbol] = candidate
    notes.append(f"turnover_budget:{turnover:.4f}->{budget:.4f}")
    return adjusted


def _current_weights(portfolio: PositionSnapshot) -> dict[str, float]:
    equity = max(portfolio.equity, 0.01)
    return {
        symbol: max(position.market_value, 0.0) / equity
        for symbol, position in portfolio.positions.items()
        if position.qty > 0 and position.market_value > 0
    }
