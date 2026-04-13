"""TOML configuration loading with only the Python standard library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import tomllib

from quant_system.agents.regime_agent import RegimeConfig
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig


@dataclass(frozen=True, slots=True)
class UniverseBucketConfig:
    enabled: bool = False
    symbols: tuple[str, ...] = ()
    include_prefixes: tuple[str, ...] = ()
    exclude_prefixes: tuple[str, ...] = ()
    exclude_st: bool = True
    exclude_suspended: bool = True
    rebalance: str | None = None


@dataclass(frozen=True, slots=True)
class UniverseConfig:
    market: str
    frequency: str
    initial_cash_cny: float
    etf_long: UniverseBucketConfig
    main_board_short: UniverseBucketConfig


@dataclass(frozen=True, slots=True)
class AgentLoopConfig:
    initial_cash_cny: float
    execution_mode: str
    lookback_days: int


def load_toml(path: Path | str) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        return tomllib.load(handle)


def load_universe_config(path: Path | str) -> UniverseConfig:
    data = load_toml(path)
    universe = _mapping(data.get("universe", {}), "universe")
    return UniverseConfig(
        market=str(universe.get("market", "cn_a_share")),
        frequency=str(universe.get("frequency", "daily")),
        initial_cash_cny=float(universe.get("initial_cash_cny", 100000.0)),
        etf_long=_load_bucket(universe.get("etf_long", {}), default_exclude_st=False),
        main_board_short=_load_bucket(universe.get("main_board_short", {})),
    )


def load_agent_loop_config(path: Path | str, fallback_initial_cash: float = 100000.0) -> AgentLoopConfig:
    data = load_toml(path)
    agent_loop = _mapping(data.get("agent_loop", {}), "agent_loop")
    return AgentLoopConfig(
        initial_cash_cny=float(agent_loop.get("initial_cash_cny", fallback_initial_cash)),
        execution_mode=str(agent_loop.get("execution_mode", "paper")),
        lookback_days=int(agent_loop.get("lookback_days", 20)),
    )


def load_regime_config(path: Path | str) -> RegimeConfig:
    data = load_toml(path)
    regime = _mapping(data.get("regime", {}), "regime")
    return RegimeConfig(
        trend_threshold=float(regime.get("trend_threshold", 0.03)),
        low_vol_threshold=float(regime.get("low_vol_threshold", 0.20)),
        trend_vol_threshold=float(regime.get("trend_vol_threshold", 0.25)),
        crisis_vol_threshold=float(regime.get("crisis_vol_threshold", 0.30)),
        crisis_corr_threshold=float(regime.get("crisis_corr_threshold", 0.70)),
    )


def load_risk_config(path: Path | str) -> RiskConfig:
    data = load_toml(path)
    risk = _mapping(data.get("risk", {}), "risk")
    return RiskConfig(
        max_position_weight=float(risk.get("max_position_weight", 0.20)),
        min_cash_buffer_pct=float(risk.get("min_cash_buffer_pct", 0.05)),
        max_daily_turnover_pct=float(risk.get("max_daily_turnover_pct", 0.50)),
        allow_chinext=bool(risk.get("allow_chinext", False)),
        allow_star=bool(risk.get("allow_star", False)),
        allow_bse=bool(risk.get("allow_bse", False)),
        allow_st=bool(risk.get("allow_st", False)),
        liquidation_only=bool(risk.get("liquidation_only", False)),
        blacklist=frozenset(str(symbol) for symbol in risk.get("blacklist", ())),
    )


def load_cost_config(path: Path | str) -> CostConfig:
    data = load_toml(path)
    cost = _mapping(data.get("cost", {}), "cost")
    return CostConfig(
        commission_rate=float(cost.get("commission_rate", 0.0003)),
        min_commission_cny=float(cost.get("min_commission_cny", 5.0)),
        stamp_tax_rate=float(cost.get("stamp_tax_rate", 0.0005)),
        transfer_fee_rate=float(cost.get("transfer_fee_rate", 0.00001)),
        slippage_bps=float(cost.get("slippage_bps", 5.0)),
    )


def _load_bucket(raw: object, *, default_exclude_st: bool = True) -> UniverseBucketConfig:
    bucket = _mapping(raw, "universe bucket")
    return UniverseBucketConfig(
        enabled=bool(bucket.get("enabled", False)),
        symbols=_tuple_of_strings(bucket.get("symbols", ())),
        include_prefixes=_tuple_of_strings(bucket.get("include_prefixes", ())),
        exclude_prefixes=_tuple_of_strings(bucket.get("exclude_prefixes", ())),
        exclude_st=bool(bucket.get("exclude_st", default_exclude_st)),
        exclude_suspended=bool(bucket.get("exclude_suspended", True)),
        rebalance=str(bucket["rebalance"]) if "rebalance" in bucket else None,
    )


def _tuple_of_strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list | tuple):
        raise TypeError(f"expected list of strings, got {type(value).__name__}")
    return tuple(str(item) for item in value)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a TOML table")
    return value
