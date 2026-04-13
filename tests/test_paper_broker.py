import unittest
from datetime import date, datetime, timezone

from quant_system.common.models import Bar, OrderIntent, OrderStatus, Side
from quant_system.execution.paper import CostConfig, PaperBroker


class PaperBrokerTest(unittest.TestCase):
    def test_fills_buy_and_settles_available_next_day(self) -> None:
        broker = PaperBroker(initial_cash=100000, cost_config=CostConfig(slippage_bps=0))
        order = OrderIntent("ord-1", "test", None, "510300", Side.BUY, 1000, 4.0, "test", datetime.now(timezone.utc))
        bar = Bar("510300", date(2025, 1, 2), open=4.0, high=4.1, low=3.9, close=4.0, volume=100000, limit_up=4.4, limit_down=3.6)
        submitted = broker.submit_orders([order], {"510300": bar})[0]
        self.assertEqual(submitted.status, OrderStatus.FILLED)
        self.assertEqual(broker.positions["510300"].qty, 1000)
        self.assertEqual(broker.positions["510300"].available_qty, 0)
        broker.settle_trading_day()
        self.assertEqual(broker.positions["510300"].available_qty, 1000)

    def test_blocks_limit_up_buy(self) -> None:
        broker = PaperBroker(initial_cash=100000, cost_config=CostConfig(slippage_bps=0))
        order = OrderIntent("ord-2", "test", None, "510300", Side.BUY, 100, 4.4, "test", datetime.now(timezone.utc))
        bar = Bar("510300", date(2025, 1, 2), open=4.4, high=4.4, low=4.4, close=4.4, volume=100000, limit_up=4.4, limit_down=3.6)
        submitted = broker.submit_orders([order], {"510300": bar})[0]
        self.assertEqual(submitted.status, OrderStatus.EXPIRED)


if __name__ == "__main__":
    unittest.main()
