"""Execution agent wrapper. MVP supports paper execution only."""

from __future__ import annotations

from datetime import date

from quant_system.common.models import Bar, Order, PositionSnapshot, ReconcileReport, RiskDecision
from quant_system.execution.paper import CostConfig, PaperBroker


class ExecutionAgent:
    def __init__(self, initial_cash: float = 100000.0, cost_config: CostConfig | None = None) -> None:
        self.broker = PaperBroker(initial_cash=initial_cash, cost_config=cost_config)

    def snapshot(self, as_of: date) -> PositionSnapshot:
        return self.broker.snapshot(as_of)

    def mark_to_market(self, bars: dict[str, Bar]) -> None:
        self.broker.mark_to_market(bars)

    def settle_trading_day(self) -> None:
        self.broker.settle_trading_day()

    def submit_approved_orders(self, decision: RiskDecision, bars: dict[str, Bar]) -> list[Order]:
        return self.broker.submit_orders(list(decision.approved_orders), bars)

    def reconcile(self, as_of: date) -> ReconcileReport:
        return self.broker.reconcile(as_of)
