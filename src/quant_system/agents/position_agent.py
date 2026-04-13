"""Position agent for deterministic target-to-order conversion."""

from __future__ import annotations

from datetime import date

from quant_system.common.models import Bar, Instrument, OrderIntent, PositionSnapshot, TargetPosition
from quant_system.portfolio.sizing import targets_to_order_intents


class PositionAgent:
    """Convert target positions into A-share order intents.

    This layer owns portfolio sizing semantics only. It does not approve risk,
    submit orders, or bypass deterministic RiskEngine checks.
    """

    def build_order_intents(
        self,
        *,
        as_of: date,
        targets: list[TargetPosition],
        portfolio: PositionSnapshot,
        bars: dict[str, Bar],
        instruments: dict[str, Instrument],
        strategy_id: str = "agent_loop",
    ) -> list[OrderIntent]:
        _ = as_of
        return targets_to_order_intents(
            strategy_id=strategy_id,
            targets=targets,
            portfolio=portfolio,
            prices=bars,
            instruments=instruments,
        )

