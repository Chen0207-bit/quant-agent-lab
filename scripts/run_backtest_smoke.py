"""Run a tiny offline backtest smoke scenario."""

from __future__ import annotations

from datetime import date, timedelta

from quant_system.backtest.engine import DailyEventBacktester
from quant_system.common.models import Bar
from quant_system.data.a_share_rules import classify_symbol
from quant_system.execution.paper import CostConfig
from quant_system.monitoring.report import render_backtest_summary
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.baseline import EtfMomentumStrategy


def main() -> None:
    symbols = ("510300",)
    instruments = {symbol: classify_symbol(symbol, name=symbol) for symbol in symbols}
    start = date(2025, 1, 1)
    bars_by_date = {}
    price = 4.0
    for idx in range(30):
        trade_date = start + timedelta(days=idx)
        price += 0.02
        bars_by_date[trade_date] = {
            "510300": Bar(
                symbol="510300",
                trade_date=trade_date,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000000,
                limit_up=price * 1.1,
                limit_down=price * 0.9,
            )
        }
    strategy = EtfMomentumStrategy(strategy_id="etf_momentum_smoke", symbols=symbols, lookback_days=5)
    result = DailyEventBacktester(
        strategy=strategy,
        instruments=instruments,
        risk_config=RiskConfig(max_position_weight=0.5),
        cost_config=CostConfig(slippage_bps=0),
    ).run(bars_by_date)
    print(render_backtest_summary(result))


if __name__ == "__main__":
    main()
