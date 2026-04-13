"""Signal aggregation agent."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from quant_system.agents.regime_agent import RegimeState
from quant_system.common.models import Bar, PositionSnapshot, StrategyDiagnosticRecord, TargetPosition
from quant_system.strategies.base import Strategy


class SignalAgent:
    def __init__(self, strategies: Sequence[Strategy]) -> None:
        self.strategies = tuple(strategies)

    def generate_targets(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
        regime: RegimeState,
    ) -> list[TargetPosition]:
        combined: dict[str, TargetPosition] = {}
        for strategy in self.strategies:
            strategy_id = strategy.strategy_id
            weight = regime.weights.get(strategy_id, regime.weights.get("default", 0.33))
            if weight <= 0:
                continue
            for target in strategy.generate_targets(as_of, history, portfolio):
                scaled_weight = target.target_weight * weight
                if scaled_weight <= 0:
                    continue
                existing = combined.get(target.symbol)
                reason = f"{strategy_id}:{target.reason}; regime={regime.regime}; weight={weight:.2f}"
                if existing is None:
                    combined[target.symbol] = TargetPosition(target.symbol, scaled_weight, reason)
                else:
                    combined[target.symbol] = TargetPosition(
                        target.symbol,
                        existing.target_weight + scaled_weight,
                        f"{existing.reason} | {reason}",
                    )
        return list(combined.values())

    def diagnose_strategies(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[StrategyDiagnosticRecord]:
        diagnostics: list[StrategyDiagnosticRecord] = []
        for strategy in self.strategies:
            diagnose = getattr(strategy, "diagnose", None)
            if callable(diagnose):
                diagnostics.extend(diagnose(as_of, history, portfolio))
        return diagnostics
