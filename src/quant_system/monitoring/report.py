"""Report helpers."""

from __future__ import annotations

from quant_system.backtest.engine import BacktestResult


def render_backtest_summary(result: BacktestResult) -> str:
    if not result.equity_curve:
        return "# Backtest Summary\n\nNo equity points."
    first = result.equity_curve[0]
    last = result.equity_curve[-1]
    ret = last.equity / first.equity - 1 if first.equity else 0.0
    return "\n".join(
        [
            "# Backtest Summary",
            "",
            f"- Start: {first.trade_date.isoformat()}",
            f"- End: {last.trade_date.isoformat()}",
            f"- Start equity: {first.equity:.2f}",
            f"- End equity: {last.equity:.2f}",
            f"- Return: {ret:.2%}",
            f"- Orders: {len(result.orders)}",
            f"- Fills: {len(result.fills)}",
            f"- Rejections: {len(result.rejected_orders)}",
        ]
    )
