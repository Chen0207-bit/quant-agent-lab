import unittest
from datetime import date, datetime, timezone

from quant_system.common.models import Bar, OrderIntent, Position, PositionSnapshot, RiskAction, Side
from quant_system.data.a_share_rules import classify_symbol
from quant_system.risk.engine import RiskConfig, RiskEngine


def order(symbol: str, side: Side, qty: int) -> OrderIntent:
    return OrderIntent(
        order_id=f"order-{symbol}-{side}",
        strategy_id="test",
        signal_id=None,
        symbol=symbol,
        side=side,
        qty=qty,
        limit_price=10.0,
        reason="test",
        created_at=datetime.now(timezone.utc),
    )


def bar(symbol: str, close: float = 10.0, volume: float = 1000000) -> Bar:
    return Bar(
        symbol=symbol,
        trade_date=date(2025, 1, 2),
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=volume,
        limit_up=close * 1.10,
        limit_down=close * 0.90,
    )


class RiskEngineTest(unittest.TestCase):
    def test_rejects_chinext_for_mvp(self) -> None:
        engine = RiskEngine()
        portfolio = PositionSnapshot(as_of=date(2025, 1, 2), cash=100000, positions={})
        decision = engine.evaluate_orders(
            as_of=date(2025, 1, 2),
            orders=[order("300750", Side.BUY, 100)],
            portfolio=portfolio,
            bars={"300750": bar("300750")},
            instruments={"300750": classify_symbol("300750")},
        )
        self.assertEqual(decision.action, RiskAction.REJECT)
        self.assertIn("outside MVP universe", decision.reasons[0])

    def test_rejects_t_plus_one_unavailable_sell(self) -> None:
        engine = RiskEngine()
        portfolio = PositionSnapshot(
            as_of=date(2025, 1, 2),
            cash=100000,
            positions={"600000": Position("600000", qty=100, available_qty=0, avg_cost=10, market_price=10)},
        )
        decision = engine.evaluate_orders(
            as_of=date(2025, 1, 2),
            orders=[order("600000", Side.SELL, 100)],
            portfolio=portfolio,
            bars={"600000": bar("600000")},
            instruments={"600000": classify_symbol("600000")},
        )
        self.assertEqual(decision.action, RiskAction.REJECT)
        self.assertIn("T+1", decision.reasons[0])

    def test_approves_valid_main_board_order(self) -> None:
        engine = RiskEngine(RiskConfig(max_position_weight=0.5))
        portfolio = PositionSnapshot(as_of=date(2025, 1, 2), cash=100000, positions={})
        decision = engine.evaluate_orders(
            as_of=date(2025, 1, 2),
            orders=[order("600000", Side.BUY, 1000)],
            portfolio=portfolio,
            bars={"600000": bar("600000")},
            instruments={"600000": classify_symbol("600000")},
        )
        self.assertEqual(decision.action, RiskAction.APPROVE)
        self.assertEqual(len(decision.approved_orders), 1)


if __name__ == "__main__":
    unittest.main()
