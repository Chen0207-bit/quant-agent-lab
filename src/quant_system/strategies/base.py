"""Strategy protocol."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from quant_system.common.models import Bar, PositionSnapshot, TargetPosition


class Strategy(Protocol):
    strategy_id: str

    def generate_targets(
        self,
        as_of: date,
        history: dict[str, list[Bar]],
        portfolio: PositionSnapshot,
    ) -> list[TargetPosition]:
        """Generate target weights using data available at `as_of` close."""
