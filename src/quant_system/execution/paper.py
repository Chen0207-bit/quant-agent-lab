"""Paper broker with A-share daily execution semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from quant_system.common.ids import new_id
from quant_system.common.models import Bar, Fill, Order, OrderIntent, OrderStatus, Position, PositionSnapshot, ReconcileReport, Side
from quant_system.data.a_share_rules import would_cross_price_limit


@dataclass(frozen=True, slots=True)
class CostConfig:
    commission_rate: float = 0.0003
    min_commission_cny: float = 5.0
    stamp_tax_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    slippage_bps: float = 5.0


class PaperBroker:
    def __init__(self, initial_cash: float, cost_config: CostConfig | None = None) -> None:
        self.cash = initial_cash
        self.cost_config = cost_config or CostConfig()
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, Order] = {}
        self.fills: list[Fill] = []

    def snapshot(self, as_of: date) -> PositionSnapshot:
        return PositionSnapshot(as_of=as_of, cash=self.cash, positions=dict(self.positions))

    def mark_to_market(self, bars: dict[str, Bar]) -> None:
        for symbol, position in self.positions.items():
            if symbol in bars:
                position.market_price = bars[symbol].close

    def submit_orders(self, orders: list[OrderIntent], bars: dict[str, Bar]) -> list[Order]:
        submitted: list[Order] = []
        for intent in orders:
            now = datetime.now(timezone.utc)
            order = Order(
                order_id=intent.order_id,
                strategy_id=intent.strategy_id,
                signal_id=intent.signal_id,
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                limit_price=intent.limit_price,
                status=OrderStatus.NEW,
                created_at=intent.created_at,
                updated_at=now,
            )
            self.orders[order.order_id] = order
            submitted.append(order)
            self._acknowledge(order)
            self._try_fill(order, bars.get(order.symbol))
        return submitted

    def settle_trading_day(self) -> None:
        for position in self.positions.values():
            position.available_qty = position.qty

    def reconcile(self, as_of: date) -> ReconcileReport:
        issues: list[str] = []
        if self.cash < -0.01:
            issues.append("negative cash")
        for position in self.positions.values():
            if position.qty < 0:
                issues.append(f"negative position: {position.symbol}")
            if position.available_qty > position.qty:
                issues.append(f"available quantity exceeds position: {position.symbol}")
        open_orders = [
            order
            for order in self.orders.values()
            if order.status in {OrderStatus.NEW, OrderStatus.ACK, OrderStatus.PARTIAL_FILL}
        ]
        if open_orders:
            issues.append(f"open orders remain: {len(open_orders)}")
        market_value = sum(position.market_value for position in self.positions.values())
        unrealized_pnl = sum(
            position.market_value - position.qty * position.avg_cost
            for position in self.positions.values()
            if position.qty > 0
        )
        return ReconcileReport(
            as_of=as_of,
            cash=self.cash,
            equity=self.cash + market_value,
            unrealized_pnl=unrealized_pnl,
            is_consistent=not issues,
            reasons=tuple(issues),
        )

    def _acknowledge(self, order: Order) -> None:
        order.status = OrderStatus.ACK
        order.updated_at = datetime.now(timezone.utc)

    def _try_fill(self, order: Order, bar: Bar | None) -> None:
        if bar is None:
            self._reject(order, "missing market bar")
            return
        if bar.is_suspended or bar.volume <= 0:
            self._reject(order, "suspended or zero-volume bar")
            return
        base_price = bar.open
        if would_cross_price_limit(order.side, base_price, bar.limit_up, bar.limit_down):
            order.status = OrderStatus.EXPIRED
            order.reject_reason = "blocked by limit price"
            order.updated_at = datetime.now(timezone.utc)
            return
        fill_price = self._slipped_price(base_price, order.side)
        if order.limit_price is not None:
            if order.side == Side.BUY and fill_price > order.limit_price:
                order.status = OrderStatus.EXPIRED
                order.reject_reason = "buy limit price not reached"
                order.updated_at = datetime.now(timezone.utc)
                return
            if order.side == Side.SELL and fill_price < order.limit_price:
                order.status = OrderStatus.EXPIRED
                order.reject_reason = "sell limit price not reached"
                order.updated_at = datetime.now(timezone.utc)
                return
        total_fee = self._total_fee(order.side, order.qty, fill_price)
        if order.side == Side.BUY and self.cash < order.qty * fill_price + total_fee:
            self._reject(order, "insufficient cash at execution")
            return
        if order.side == Side.SELL:
            position = self.positions.get(order.symbol)
            if position is None or position.available_qty < order.qty:
                self._reject(order, "insufficient available quantity at execution")
                return
        self._apply_fill(order, fill_price)

    def _apply_fill(self, order: Order, price: float) -> None:
        now = datetime.now(timezone.utc)
        commission = self._commission(order.qty, price)
        stamp_tax = self._stamp_tax(order.side, order.qty, price)
        transfer_fee = self._transfer_fee(order.qty, price)
        fill = Fill(
            fill_id=new_id("fill"),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=price,
            commission=commission,
            stamp_tax=stamp_tax,
            transfer_fee=transfer_fee,
            slippage=abs(price - order.limit_price) if order.limit_price is not None else 0.0,
            timestamp=now,
        )
        if order.side == Side.BUY:
            self._apply_buy(fill)
        else:
            self._apply_sell(fill)
        order.filled_qty = fill.qty
        order.avg_fill_price = fill.price
        order.status = OrderStatus.FILLED
        order.updated_at = now
        self.fills.append(fill)

    def _apply_buy(self, fill: Fill) -> None:
        total_cost = fill.notional + fill.commission + fill.stamp_tax + fill.transfer_fee
        self.cash -= total_cost
        position = self.positions.setdefault(fill.symbol, Position(symbol=fill.symbol))
        new_qty = position.qty + fill.qty
        position.avg_cost = ((position.avg_cost * position.qty) + fill.notional) / new_qty
        position.qty = new_qty
        position.market_price = fill.price

    def _apply_sell(self, fill: Fill) -> None:
        total_fee = fill.commission + fill.stamp_tax + fill.transfer_fee
        self.cash += fill.notional - total_fee
        position = self.positions[fill.symbol]
        position.qty -= fill.qty
        position.available_qty -= fill.qty
        position.market_price = fill.price
        if position.qty == 0:
            position.avg_cost = 0.0

    def _reject(self, order: Order, reason: str) -> None:
        order.status = OrderStatus.REJECTED
        order.reject_reason = reason
        order.updated_at = datetime.now(timezone.utc)

    def _slipped_price(self, price: float, side: Side) -> float:
        if side == Side.BUY:
            return price * (1 + self.cost_config.slippage_bps / 10000)
        return price * (1 - self.cost_config.slippage_bps / 10000)

    def _commission(self, qty: int, price: float) -> float:
        return max(qty * price * self.cost_config.commission_rate, self.cost_config.min_commission_cny)

    def _stamp_tax(self, side: Side, qty: int, price: float) -> float:
        return qty * price * self.cost_config.stamp_tax_rate if side == Side.SELL else 0.0

    def _transfer_fee(self, qty: int, price: float) -> float:
        return qty * price * self.cost_config.transfer_fee_rate

    def _total_fee(self, side: Side, qty: int, price: float) -> float:
        return self._commission(qty, price) + self._stamp_tax(side, qty, price) + self._transfer_fee(qty, price)
