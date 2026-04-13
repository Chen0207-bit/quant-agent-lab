"""Convert target weights into A-share order intents."""

from __future__ import annotations

from datetime import datetime, timezone

from quant_system.common.ids import new_id
from quant_system.common.models import Bar, Instrument, OrderIntent, PositionSnapshot, Side, TargetPosition
from quant_system.data.a_share_rules import round_to_lot


def targets_to_order_intents(
    *,
    strategy_id: str,
    targets: list[TargetPosition],
    portfolio: PositionSnapshot,
    prices: dict[str, Bar],
    instruments: dict[str, Instrument],
) -> list[OrderIntent]:
    target_by_symbol = {target.symbol: target for target in targets}
    symbols = set(target_by_symbol) | set(portfolio.positions)
    orders: list[OrderIntent] = []
    equity = portfolio.equity
    created_at = datetime.now(timezone.utc)

    for symbol in sorted(symbols):
        bar = prices.get(symbol)
        instrument = instruments.get(symbol)
        if bar is None or instrument is None:
            continue
        target = target_by_symbol.get(symbol)
        target_weight = target.target_weight if target else 0.0
        current_qty = portfolio.positions.get(symbol).qty if symbol in portfolio.positions else 0
        target_notional = max(target_weight, 0.0) * equity
        target_qty = round_to_lot(int(target_notional / bar.close), instrument.lot_size)
        delta_qty = target_qty - current_qty
        if delta_qty == 0:
            continue
        side = Side.BUY if delta_qty > 0 else Side.SELL
        orders.append(
            OrderIntent(
                order_id=new_id("ord"),
                strategy_id=strategy_id,
                signal_id=None,
                symbol=symbol,
                side=side,
                qty=abs(delta_qty),
                limit_price=None,
                reason=target.reason if target else "rebalance_to_zero",
                created_at=created_at,
            )
        )
    return orders
