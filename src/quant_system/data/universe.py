"""Universe construction and snapshots for the A-share MVP."""

from __future__ import annotations

from datetime import date
from typing import Mapping

from quant_system.common.models import Bar, Instrument, UniverseMember, UniverseSnapshot
from quant_system.config.settings import UniverseBucketConfig, UniverseConfig, UniverseSymbolMetadata
from quant_system.data.a_share_rules import classify_symbol, is_mvp_allowed_instrument


def build_mvp_universe(config: UniverseConfig) -> dict[str, Instrument]:
    instruments: dict[str, Instrument] = {}
    if config.etf_long.enabled:
        _add_bucket(instruments, config.etf_long)
    if config.main_board_short.enabled:
        _add_bucket(instruments, config.main_board_short)
    return instruments


def build_universe_snapshot(
    as_of: date,
    instruments: Mapping[str, Instrument],
    bars: Mapping[str, Bar],
    config: UniverseConfig | None = None,
) -> UniverseSnapshot:
    metadata = config.symbol_metadata if config is not None else {}
    members: dict[str, UniverseMember] = {}
    for symbol, instrument in instruments.items():
        bar = bars.get(symbol)
        meta = metadata.get(symbol, UniverseSymbolMetadata())
        industry = meta.industry
        if not industry or industry == "unknown":
            industry = "ETF" if instrument.board.value == "ETF" else "unknown"
        members[symbol] = UniverseMember(
            symbol=symbol,
            board=instrument.board.value,
            asset_type=instrument.asset_type.value,
            industry=industry,
            liquidity_cny=_traded_amount(bar),
            free_float_mkt_cap=meta.free_float_mkt_cap,
            is_st=instrument.is_st,
            is_suspended=instrument.is_suspended or (bar.is_suspended if bar is not None else False),
            price_limit_pct=instrument.price_limit_pct,
            style_tags=meta.style_tags,
            fundamentals=dict(meta.fundamentals),
        )
    return UniverseSnapshot(as_of=as_of, members=members)


def _add_bucket(instruments: dict[str, Instrument], bucket: UniverseBucketConfig) -> None:
    for symbol in bucket.symbols:
        clean_symbol = symbol.strip().split(".")[0]
        if not clean_symbol or not _symbol_allowed_by_prefix(clean_symbol, bucket):
            continue
        instrument = classify_symbol(clean_symbol)
        if bucket.exclude_st and instrument.is_st:
            continue
        if bucket.exclude_suspended and instrument.is_suspended:
            continue
        if not is_mvp_allowed_instrument(instrument):
            continue
        instruments[clean_symbol] = instrument


def _symbol_allowed_by_prefix(symbol: str, bucket: UniverseBucketConfig) -> bool:
    if bucket.include_prefixes and not symbol.startswith(bucket.include_prefixes):
        return False
    if bucket.exclude_prefixes and symbol.startswith(bucket.exclude_prefixes):
        return False
    return True


def _traded_amount(bar: Bar | None) -> float:
    if bar is None:
        return 0.0
    if bar.amount > 0:
        return bar.amount
    return bar.volume * bar.close
