"""Offline paper trading smoke entrypoint."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from quant_system.common.models import Bar, OrderIntent, Side
from quant_system.data.a_share_rules import classify_symbol
from quant_system.execution.paper import CostConfig, PaperBroker
from quant_system.risk.engine import RiskConfig, RiskEngine


def main() -> None:
    symbol = "510300"
    as_of = date(2025, 1, 2)
    instrument = classify_symbol(symbol)
    bar = Bar(symbol, as_of, open=4.0, high=4.1, low=3.9, close=4.0, volume=1000000, limit_up=4.4, limit_down=3.6)
    order = OrderIntent("paper-smoke-1", "paper_smoke", None, symbol, Side.BUY, 1000, None, "offline smoke", datetime.now(timezone.utc))
    broker = PaperBroker(initial_cash=100000, cost_config=CostConfig(slippage_bps=0))
    snapshot = broker.snapshot(as_of)
    decision = RiskEngine(RiskConfig(max_position_weight=0.5)).evaluate_orders(
        as_of=as_of,
        orders=[order],
        portfolio=snapshot,
        bars={symbol: bar},
        instruments={symbol: instrument},
    )
    submitted = broker.submit_orders(list(decision.approved_orders), {symbol: bar})
    reconcile = broker.reconcile(as_of)
    print(
        json.dumps(
            {
                "component": "paper_run_smoke",
                "risk_action": decision.action.value,
                "orders": [order.status.value for order in submitted],
                "fills": len(broker.fills),
                "cash": round(broker.cash, 2),
                "consistent": reconcile.is_consistent,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
