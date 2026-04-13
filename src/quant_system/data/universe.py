"""Universe construction for the A-share MVP."""

from __future__ import annotations

from quant_system.common.models import Instrument
from quant_system.config.settings import UniverseBucketConfig, UniverseConfig
from quant_system.data.a_share_rules import classify_symbol, is_mvp_allowed_instrument


def build_mvp_universe(config: UniverseConfig) -> dict[str, Instrument]:
    instruments: dict[str, Instrument] = {}
    if config.etf_long.enabled:
        _add_bucket(instruments, config.etf_long)
    if config.main_board_short.enabled:
        _add_bucket(instruments, config.main_board_short)
    return instruments


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
