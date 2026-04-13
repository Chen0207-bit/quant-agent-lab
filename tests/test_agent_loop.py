import unittest
from datetime import date, timedelta

from quant_system.app.main_loop import ModularAgentLoop
from quant_system.common.models import Bar
from quant_system.data.a_share_rules import classify_symbol
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.baseline import EtfMomentumStrategy


class AgentLoopTest(unittest.TestCase):
    def test_offline_agent_loop_produces_summary_and_fills(self) -> None:
        symbol = "510300"
        instruments = {symbol: classify_symbol(symbol)}
        bars_by_date = {}
        price = 4.0
        start = date(2025, 1, 1)
        for idx in range(30):
            price += 0.02
            trade_date = start + timedelta(days=idx)
            bars_by_date[trade_date] = {symbol: Bar(symbol, trade_date, price, price * 1.01, price * 0.99, price, 1000000, limit_up=price * 1.1, limit_down=price * 0.9)}
        loop = ModularAgentLoop(
            strategies=(EtfMomentumStrategy("etf_momentum", symbols=(symbol,), lookback_days=5, max_weight_per_symbol=0.4),),
            instruments=instruments,
            risk_config=RiskConfig(max_position_weight=0.5),
            cost_config=CostConfig(slippage_bps=0),
        )
        results = loop.run(bars_by_date)
        self.assertEqual(len(results), 30)
        self.assertIn("Daily Agent Summary", results[-1].summary)
        self.assertGreaterEqual(len(results[-1].fills), 1)


if __name__ == "__main__":
    unittest.main()
