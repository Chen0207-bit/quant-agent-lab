"""Deterministic A-share risk engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from quant_system.common.models import (
    Bar,
    Board,
    Instrument,
    OrderIntent,
    PositionSnapshot,
    RiskAction,
    RiskDecision,
    RiskRejection,
    Side,
)
from quant_system.data.a_share_rules import is_mvp_allowed_instrument, would_cross_price_limit


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_position_weight: float = 0.20
    min_cash_buffer_pct: float = 0.05
    max_daily_turnover_pct: float = 0.50
    allow_chinext: bool = False
    allow_star: bool = False
    allow_bse: bool = False
    allow_st: bool = False
    liquidation_only: bool = False
    blacklist: frozenset[str] = field(default_factory=frozenset)


class RiskEngine:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def evaluate_orders(
        self,
        *,
        as_of: date,
        orders: list[OrderIntent],
        portfolio: PositionSnapshot,
        bars: dict[str, Bar],
        instruments: dict[str, Instrument],
    ) -> RiskDecision:
        approved: list[OrderIntent] = []
        rejections: list[RiskRejection] = []
        equity = max(portfolio.equity, portfolio.cash, 0.01)
        projected_cash = portfolio.cash
        projected_turnover = 0.0

        for order in orders:
            reason = self._reject_reason(order, portfolio, bars, instruments)
            bar = bars.get(order.symbol)
            notional = order.qty * (bar.close if bar else 0.0)

            if reason is None and self.config.liquidation_only and order.side == Side.BUY:
                reason = "liquidation_only rejects buy order"
            if reason is None and order.side == Side.BUY:
                min_cash = self.config.min_cash_buffer_pct * equity
                if projected_cash - notional < min_cash:
                    reason = "cash buffer would be breached"
                else:
                    projected_cash -= notional
            if reason is None and order.side == Side.SELL:
                projected_cash += notional
            if reason is None:
                projected_turnover += notional
                if projected_turnover > self.config.max_daily_turnover_pct * equity:
                    reason = "daily turnover limit breached"
            if reason is None and order.side == Side.BUY and bar is not None:
                current_qty = portfolio.positions.get(order.symbol).qty if order.symbol in portfolio.positions else 0
                projected_value = (current_qty + order.qty) * bar.close
                if projected_value > self.config.max_position_weight * equity:
                    reason = "single-name concentration limit breached"
            if reason is None:
                approved.append(order)
            else:
                rejections.append(RiskRejection(order.order_id, order.symbol, reason))

        action = RiskAction.APPROVE if not rejections else RiskAction.REJECT
        return RiskDecision(action, tuple(approved), tuple(rejections), tuple(r.reason for r in rejections))

    def _reject_reason(
        self,
        order: OrderIntent,
        portfolio: PositionSnapshot,
        bars: dict[str, Bar],
        instruments: dict[str, Instrument],
    ) -> str | None:
        instrument = instruments.get(order.symbol)
        bar = bars.get(order.symbol)
        if instrument is None:
            return "missing instrument"
        if bar is None:
            return "missing market bar"
        if order.qty <= 0:
            return "non-positive quantity"
        if order.qty % instrument.lot_size != 0:
            return "quantity is not aligned to lot size"
        if order.symbol in self.config.blacklist:
            return "symbol is blacklisted"
        if instrument.is_st and not self.config.allow_st:
            return "ST instrument is not allowed"
        if instrument.is_suspended or bar.is_suspended or bar.volume <= 0:
            return "instrument is suspended or has no volume"
        if not is_mvp_allowed_instrument(instrument):
            return "instrument is outside MVP universe"
        if instrument.board == Board.CHINEXT and not self.config.allow_chinext:
            return "ChiNext is not allowed"
        if instrument.board == Board.STAR and not self.config.allow_star:
            return "STAR market is not allowed"
        if instrument.board == Board.BSE and not self.config.allow_bse:
            return "BSE is not allowed"
        if would_cross_price_limit(order.side, bar.close, bar.limit_up, bar.limit_down):
            return "order would trade at blocked limit price"
        if order.side == Side.SELL:
            position = portfolio.positions.get(order.symbol)
            available_qty = position.available_qty if position else 0
            if order.qty > available_qty:
                return "T+1 available quantity is insufficient"
        return None
