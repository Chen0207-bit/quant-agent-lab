"""Run the modular multi-agent loop on offline synthetic data."""

from __future__ import annotations

from datetime import date, timedelta

from quant_system.app.main_loop import ModularAgentLoop
from quant_system.common.models import Bar
from quant_system.data.a_share_rules import classify_symbol
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.baseline import EtfMomentumStrategy, MainBoardBreakoutStrategy


def main() -> None:
    symbols = ("510300", "600000")
    instruments = {symbol: classify_symbol(symbol) for symbol in symbols}
    bars_by_date = _sample_bars(symbols)
    loop = ModularAgentLoop(
        strategies=(
            EtfMomentumStrategy("etf_momentum", symbols=("510300",), lookback_days=5, max_weight_per_symbol=0.40),
            MainBoardBreakoutStrategy("main_board_breakout", symbols=("600000",), lookback_days=5, max_weight_per_symbol=0.10),
        ),
        instruments=instruments,
        risk_config=RiskConfig(max_position_weight=0.5),
        cost_config=CostConfig(slippage_bps=0),
    )
    results = loop.run(bars_by_date)
    print(results[-1].summary)


def _sample_bars(symbols: tuple[str, ...]) -> dict[date, dict[str, Bar]]:
    start = date(2025, 1, 1)
    bars_by_date: dict[date, dict[str, Bar]] = {}
    etf_price = 4.0
    stock_price = 10.0
    for idx in range(30):
        trade_date = start + timedelta(days=idx)
        etf_price += 0.02
        stock_price += 0.06 if idx > 5 else 0.01
        bars_by_date[trade_date] = {
            "510300": _bar("510300", trade_date, etf_price),
            "600000": _bar("600000", trade_date, stock_price),
        }
    return bars_by_date


def _bar(symbol: str, trade_date: date, price: float) -> Bar:
    return Bar(
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


if __name__ == "__main__":
    main()
