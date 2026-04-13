"""Run the modular multi-agent loop from locally synced Parquet data."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from quant_system.app.main_loop import ModularAgentLoop
from quant_system.common.models import Bar
from quant_system.data.a_share_rules import classify_symbol
from quant_system.data.manager import DataManager
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.baseline import EtfMomentumStrategy, MainBoardBreakoutStrategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run agent loop from local Parquet data.")
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols")
    parser.add_argument("--data-dir", default="runs/data", help="Local data directory")
    parser.add_argument("--dataset", default="silver", choices=["silver", "gold"], help="Dataset to read")
    parser.add_argument("--lookback-days", type=int, default=5, help="Strategy lookback days for small-sample validation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = _parse_date(args.start)
    end = _parse_date(args.end)
    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    manager = DataManager(data_dir=Path(args.data_dir))
    history = {symbol: manager.get_history(symbol, start_date=start, end_date=end, dataset=args.dataset) for symbol in symbols}
    missing = [symbol for symbol, bars in history.items() if not bars]
    if missing:
        raise SystemExit(f"No local bars for {missing}. Run scripts/data_sync_akshare.py first.")
    bars_by_date = _group_by_date(history)
    instruments = {symbol: classify_symbol(symbol) for symbol in symbols}
    loop = ModularAgentLoop(
        strategies=(
            EtfMomentumStrategy("etf_momentum", symbols=tuple(symbols), lookback_days=args.lookback_days, max_weight_per_symbol=0.40),
            MainBoardBreakoutStrategy("main_board_breakout", symbols=tuple(symbols), lookback_days=args.lookback_days, max_weight_per_symbol=0.10),
        ),
        instruments=instruments,
        risk_config=RiskConfig(max_position_weight=0.5),
        cost_config=CostConfig(),
    )
    results = loop.run(bars_by_date)
    if not results:
        raise SystemExit("No agent loop results produced.")
    print(results[-1].summary)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _group_by_date(history: dict[str, list[Bar]]) -> dict[date, dict[str, Bar]]:
    grouped: dict[date, dict[str, Bar]] = {}
    for symbol, bars in history.items():
        for bar in bars:
            grouped.setdefault(bar.trade_date, {})[symbol] = bar
    return {trade_date: grouped[trade_date] for trade_date in sorted(grouped)}


if __name__ == "__main__":
    main()
