"""Strategy protocols."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from quant_system.common.models import (
    Bar,
    PositionSnapshot,
    ScoredCandidate,
    StrategyContext,
    StrategyDiagnosticRecord,
    TargetPosition,
)


class Strategy(Protocol):
    strategy_id: str

    def generate_targets(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[TargetPosition]:
        """Generate target weights using data available at `as_of` close."""


@runtime_checkable
class CrossSectionalStrategy(Protocol):
    strategy_id: str
    family: str
    rebalance_frequency: str

    def rank_candidates(
        self,
        context: StrategyContext,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[ScoredCandidate]:
        """Rank the available universe and return scored candidates."""

    def diagnose(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
        context: StrategyContext | None = None,
    ) -> list[StrategyDiagnosticRecord]:
        """Return audit-friendly diagnostics for the current strategy."""

    def is_rebalance_day(self, as_of: date, history: dict[str, list[Bar]]) -> bool:
        """Return True when the strategy is allowed to refresh holdings."""
