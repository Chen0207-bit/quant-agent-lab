"""Manual order export for human-confirmed trading."""

from __future__ import annotations

import csv
from pathlib import Path

from quant_system.common.models import OrderIntent


def export_manual_orders(path: Path, orders: list[OrderIntent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["order_id", "strategy_id", "signal_id", "symbol", "side", "qty", "limit_price", "reason", "created_at"],
        )
        writer.writeheader()
        for order in orders:
            writer.writerow(
                {
                    "order_id": order.order_id,
                    "strategy_id": order.strategy_id,
                    "signal_id": order.signal_id or "",
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "qty": order.qty,
                    "limit_price": order.limit_price or "",
                    "reason": order.reason,
                    "created_at": order.created_at.isoformat(),
                }
            )
