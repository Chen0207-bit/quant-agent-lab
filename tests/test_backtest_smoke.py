import unittest
from datetime import date, timedelta

from quant_system.backtest.engine import DailyEventBacktester
from quant_system.common.models import Bar
from quant_system.data.a_share_rules import classify_symbol
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.baseline import EtfMomentumStrategy


class BacktestSmokeTest(unittest.TestCase):
    def test_daily_event_backtest_smoke_runs(self) -> None:
        symbol = "510300"
        instruments = {symbol: classify_symbol(symbol)}
        bars_by_date = {}
        start = date(2025, 1, 1)
        price = 4.0
        for idx in range(30):
            trade_date = start + timedelta(days=idx)
            price += 0.03
            bars_by_date[trade_date] = {
                symbol: Bar(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=price,
                    high=price * 1.01,
                    low=price * 0.99,
                    close=price,
                    volume=1000000,
                    limit_up=price * 1.10,
                    limit_down=price * 0.90,
                )
            }
        strategy = EtfMomentumStrategy(
            strategy_id="etf_momentum_test",
            symbols=(symbol,),
            lookback_days=5,
            top_n=1,
            max_weight_per_symbol=0.2,
        )
        result = DailyEventBacktester(
            strategy=strategy,
            instruments=instruments,
            risk_config=RiskConfig(max_position_weight=0.3),
            cost_config=CostConfig(slippage_bps=0),
        ).run(bars_by_date)
        self.assertEqual(len(result.equity_curve), 30)
        self.assertGreaterEqual(len(result.orders), 1)
        self.assertGreater(result.equity_curve[-1].equity, 0)


if __name__ == "__main__":
    unittest.main()
