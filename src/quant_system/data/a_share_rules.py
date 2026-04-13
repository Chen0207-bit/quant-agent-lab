"""A-share symbol and trading-rule helpers."""

from __future__ import annotations

from math import floor

from quant_system.common.models import AssetType, Board, Exchange, Instrument, Side

ETF_PREFIXES = ("510", "511", "512", "513", "515", "516", "517", "518", "588", "159", "160", "161", "162")


def classify_symbol(symbol: str, name: str = "") -> Instrument:
    clean = symbol.split(".")[0]
    if clean.startswith(ETF_PREFIXES):
        exchange = Exchange.SSE if clean.startswith(("51", "58")) else Exchange.SZSE
        return Instrument(clean, name or clean, exchange, Board.ETF, AssetType.ETF, is_st=_is_st_name(name))
    if clean.startswith(("600", "601", "603", "605")):
        return Instrument(clean, name or clean, Exchange.SSE, Board.MAIN, AssetType.STOCK)
    if clean.startswith(("000", "001", "002", "003")):
        return Instrument(clean, name or clean, Exchange.SZSE, Board.MAIN, AssetType.STOCK)
    if clean.startswith(("300", "301")):
        return Instrument(clean, name or clean, Exchange.SZSE, Board.CHINEXT, AssetType.STOCK, price_limit_pct=0.20)
    if clean.startswith(("688", "689")):
        return Instrument(clean, name or clean, Exchange.SSE, Board.STAR, AssetType.STOCK, price_limit_pct=0.20)
    if clean.startswith(("8", "4")):
        return Instrument(clean, name or clean, Exchange.BSE, Board.BSE, AssetType.STOCK, price_limit_pct=0.30)
    return Instrument(clean, name or clean, Exchange.UNKNOWN, Board.UNKNOWN, AssetType.STOCK)


def is_mvp_allowed_instrument(instrument: Instrument) -> bool:
    if instrument.is_st or instrument.is_suspended:
        return False
    return instrument.board in {Board.MAIN, Board.ETF}


def round_to_lot(quantity: int, lot_size: int = 100) -> int:
    if quantity <= 0:
        return 0
    return floor(quantity / lot_size) * lot_size


def would_cross_price_limit(side: Side, price: float, limit_up: float | None, limit_down: float | None) -> bool:
    if side == Side.BUY and limit_up is not None and price >= limit_up:
        return True
    if side == Side.SELL and limit_down is not None and price <= limit_down:
        return True
    return False


def _is_st_name(name: str) -> bool:
    upper_name = name.upper()
    return "ST" in upper_name or "\u9000" in name
