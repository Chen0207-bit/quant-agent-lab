"""Risk agent wrapper around the deterministic RiskEngine."""

from __future__ import annotations

from datetime import date

from quant_system.common.models import Bar, Instrument, OrderIntent, PositionSnapshot, RiskDecision
from quant_system.risk.engine import RiskConfig, RiskEngine


class RiskAgent:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.engine = RiskEngine(config)

    def review_orders(
        self,
        *,
        as_of: date,
        orders: list[OrderIntent],
        portfolio: PositionSnapshot,
        bars: dict[str, Bar],
        instruments: dict[str, Instrument],
    ) -> RiskDecision:
        return self.engine.evaluate_orders(
            as_of=as_of,
            orders=orders,
            portfolio=portfolio,
            bars=bars,
            instruments=instruments,
        )
