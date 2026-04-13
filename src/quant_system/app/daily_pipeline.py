"""Daily end-of-day pipeline for the A-share modular agent loop."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence

from quant_system.agents.data_agent import DataAgent, DataAgentError
from quant_system.agents.monitor_agent import MonitorAgent
from quant_system.agents.regime_agent import RegimeAgent
from quant_system.app.main_loop import AgentLoopResult, ModularAgentLoop
from quant_system.common.ids import new_run_id
from quant_system.common.models import Bar, Board, Instrument, StrategyDiagnosticRecord
from quant_system.config.settings import (
    load_agent_loop_config,
    load_cost_config,
    load_llm_config,
    load_regime_config,
    load_risk_config,
    load_toml,
    load_universe_config,
)
from quant_system.data.a_share_rules import classify_symbol, is_mvp_allowed_instrument
from quant_system.data.calendar import TradingCalendar
from quant_system.data.manager import DataManager, DataSyncReport
from quant_system.data.universe import build_mvp_universe, build_universe_snapshot
from quant_system.llm import DisabledLLMClient, LLMReportAgent, load_report_artifacts
from quant_system.strategies.baseline import EtfMomentumStrategy, MainBoardBreakoutStrategy
from quant_system.strategies.base import Strategy


@dataclass(frozen=True, slots=True)
class DailyPipelineResult:
    as_of: date
    symbols: tuple[str, ...]
    report_dir: Path
    data_sync_report: DataSyncReport
    agent_result: AgentLoopResult


class DailyPipelineError(RuntimeError):
    pass


def run_daily_pipeline(
    *,
    as_of: date | None = None,
    config_dir: Path | str = Path("configs"),
    data_dir: Path | str = Path("runs/data"),
    report_dir: Path | str = Path("runs/reports"),
    symbols: Sequence[str] | None = None,
    start: date | None = None,
    dataset: str = "silver",
    lookback_days: int | None = None,
    max_retries: int = 3,
    retry_backoff_seconds: float = 1.0,
    calendar: TradingCalendar | None = None,
    data_manager: DataManager | None = None,
) -> DailyPipelineResult:
    config_path = Path(config_dir)
    data_path = Path(data_dir)
    report_base = Path(report_dir)

    universe_config = load_universe_config(config_path / "universe.toml")
    configured_universe = build_mvp_universe(universe_config)
    selected_symbols = _resolve_symbols(symbols, configured_universe)
    instruments = _resolve_instruments(selected_symbols, configured_universe)

    strategy_path = config_path / "strategy.toml"
    llm_config = load_llm_config(config_path / "llm.toml")
    agent_loop_config = load_agent_loop_config(
        strategy_path,
        fallback_initial_cash=universe_config.initial_cash_cny,
    )
    if agent_loop_config.execution_mode != "paper":
        raise DailyPipelineError("MVP daily pipeline only supports paper execution")

    requested_lookback = lookback_days if lookback_days is not None else agent_loop_config.lookback_days
    strategy_lookback = _max_strategy_lookback(strategy_path, requested_lookback)
    history_lookback = max(requested_lookback, strategy_lookback)
    calendar_end = as_of if as_of is not None else date.today() - timedelta(days=1)
    calendar_start = start or calendar_end - timedelta(days=max(history_lookback * 3, 120))
    active_calendar = calendar or TradingCalendar.from_akshare(data_path, calendar_start, calendar_end)
    effective_as_of = active_calendar.latest_trading_day(calendar_end)
    output_dir = report_base / effective_as_of.isoformat()

    manager = data_manager or DataManager(
        data_dir=data_path,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    data_agent = DataAgent(manager=manager, calendar=active_calendar, dataset=dataset)
    try:
        data_result = data_agent.prepare_history(
            as_of=calendar_end,
            symbols=selected_symbols,
            lookback_days=history_lookback,
            start=start,
        )
    except DataAgentError as exc:
        if exc.sync_report is not None:
            _write_failed_sync_report(output_dir, exc.sync_report)
        raise DailyPipelineError(str(exc)) from exc
    sync_report = data_result.sync_report
    bars_by_date = data_result.bars_by_date

    monitor = MonitorAgent()
    loop = ModularAgentLoop(
        strategies=_build_strategies(
            strategy_path=strategy_path,
            instruments=instruments,
            lookback_days_override=lookback_days,
            default_lookback_days=agent_loop_config.lookback_days,
        ),
        instruments=instruments,
        initial_cash=agent_loop_config.initial_cash_cny,
        risk_config=load_risk_config(config_path / "risk.toml"),
        cost_config=load_cost_config(config_path / "cost.toml"),
        regime_agent=RegimeAgent(load_regime_config(strategy_path)),
        monitor_agent=monitor,
        universe_config=universe_config,
    )
    results = loop.run(bars_by_date)
    if not results:
        raise DailyPipelineError("agent loop produced no results")
    latest_result = results[-1]
    if latest_result.as_of != effective_as_of:
        raise DailyPipelineError(
            "latest local data does not match calendar as_of: "
            f"{latest_result.as_of.isoformat()} != {effective_as_of.isoformat()}"
        )

    diagnostics_path = output_dir / "strategy_diagnostics.json"
    daily_summary_json = _render_daily_json(
        monitor=monitor,
        result=latest_result,
        symbols=selected_symbols,
        data_sync_report=sync_report,
        strategy_diagnostics_path=diagnostics_path,
    )
    output_paths = monitor.write_daily_outputs(
        report_dir=output_dir,
        daily_summary=latest_result.summary,
        daily_summary_json=daily_summary_json,
        manual_orders=list(latest_result.risk_decision.approved_orders),
        data_sync_report=sync_report,
        strategy_diagnostics_json=_render_strategy_diagnostics_json(latest_result),
    )
    universe_snapshot = build_universe_snapshot(
        effective_as_of,
        instruments,
        bars_by_date.get(effective_as_of, {}),
        universe_config,
    )
    (output_dir / "universe_snapshot.json").write_text(
        json.dumps(asdict(universe_snapshot), ensure_ascii=True, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    if llm_config.report_agent.enabled:
        report_artifacts = load_report_artifacts(output_dir)
        report_agent = LLMReportAgent(
            client=DisabledLLMClient(provider=llm_config.provider, model=llm_config.model),
            enabled=llm_config.enabled,
            provider=llm_config.provider,
            model=llm_config.model,
        )
        report_agent.review_daily_report(report_artifacts, run_id=new_run_id("llm_report"))
    return DailyPipelineResult(
        as_of=effective_as_of,
        symbols=selected_symbols,
        report_dir=output_dir,
        data_sync_report=sync_report,
        agent_result=latest_result,
    )


def _resolve_symbols(
    symbols: Sequence[str] | None,
    configured_universe: Mapping[str, Instrument],
) -> tuple[str, ...]:
    if symbols:
        resolved = tuple(dict.fromkeys(symbol.strip().split(".")[0] for symbol in symbols if symbol.strip()))
    else:
        resolved = tuple(configured_universe)
    if not resolved:
        raise DailyPipelineError("daily pipeline universe is empty")
    return resolved


def _resolve_instruments(
    symbols: Sequence[str],
    configured_universe: Mapping[str, Instrument],
) -> dict[str, Instrument]:
    instruments: dict[str, Instrument] = {}
    rejected: list[str] = []
    for symbol in symbols:
        instrument = configured_universe.get(symbol) or classify_symbol(symbol)
        if not is_mvp_allowed_instrument(instrument):
            rejected.append(symbol)
            continue
        instruments[symbol] = instrument
    if rejected:
        raise DailyPipelineError("symbols outside MVP universe: " + ", ".join(rejected))
    if not instruments:
        raise DailyPipelineError("no allowed instruments in selected universe")
    return instruments


def _build_strategies(
    *,
    strategy_path: Path,
    instruments: Mapping[str, Instrument],
    lookback_days_override: int | None,
    default_lookback_days: int,
) -> tuple[Strategy, ...]:
    data = load_toml(strategy_path)
    strategy_root = data.get("strategy", {})
    strategy_config = strategy_root if isinstance(strategy_root, dict) else {}
    etf_config = _table(strategy_config.get("etf_momentum", {}))
    main_config = _table(strategy_config.get("main_board_breakout", {}))
    etf_symbols = tuple(symbol for symbol, instrument in instruments.items() if instrument.board == Board.ETF)
    main_symbols = tuple(symbol for symbol, instrument in instruments.items() if instrument.board == Board.MAIN)

    strategies: list[Strategy] = []
    if bool(etf_config.get("enabled", True)) and etf_symbols:
        etf_lookback_days = _lookback_value(etf_config, lookback_days_override, default_lookback_days)
        strategies.append(
            EtfMomentumStrategy(
                "etf_momentum",
                symbols=etf_symbols,
                lookback_days=etf_lookback_days,
                lookback_windows=_tuple_ints(etf_config.get("lookback_windows", ())),
                window_weights=_tuple_floats(etf_config.get("window_weights", ())),
                volatility_window=int(etf_config.get("volatility_window", 60)),
                volatility_penalty=float(etf_config.get("volatility_penalty", 0.25)),
                top_n=int(etf_config.get("top_n", 2)),
                min_momentum=float(etf_config.get("min_momentum", 0.0)),
                max_weight_per_symbol=float(etf_config.get("max_weight_per_symbol", 0.25)),
            )
        )
    if bool(main_config.get("enabled", True)) and main_symbols:
        main_lookback_days = _lookback_value(main_config, lookback_days_override, default_lookback_days)
        strategies.append(
            MainBoardBreakoutStrategy(
                "main_board_breakout",
                symbols=main_symbols,
                lookback_days=main_lookback_days,
                top_n=int(main_config.get("top_n", 5)),
                max_weight_per_symbol=float(main_config.get("max_weight_per_symbol", 0.15)),
                min_amount_cny=float(main_config.get("min_amount_cny", 10_000_000.0)),
                moving_average_days=int(main_config.get("moving_average_days", main_lookback_days)),
            )
        )
    if not strategies:
        raise DailyPipelineError("no enabled strategies for selected universe")
    return tuple(strategies)


def _max_strategy_lookback(strategy_path: Path, fallback_lookback_days: int) -> int:
    data = load_toml(strategy_path)
    strategy_root = data.get("strategy", {})
    strategy_config = strategy_root if isinstance(strategy_root, dict) else {}
    etf_config = _table(strategy_config.get("etf_momentum", {}))
    main_config = _table(strategy_config.get("main_board_breakout", {}))
    etf_windows = _tuple_ints(etf_config.get("lookback_windows", ()))
    candidates = [fallback_lookback_days]
    if etf_windows:
        candidates.extend(etf_windows)
    else:
        candidates.append(int(etf_config.get("lookback_days", fallback_lookback_days)))
    candidates.append(int(etf_config.get("volatility_window", 60)))
    candidates.append(int(main_config.get("lookback_days", fallback_lookback_days)))
    candidates.append(int(main_config.get("moving_average_days", main_config.get("lookback_days", fallback_lookback_days))))
    return max(value for value in candidates if value > 0)


def _lookback_value(config: dict[str, object], override: int | None, default: int) -> int:
    if override is not None:
        return override
    return int(config.get("lookback_days", default))


def _table(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _tuple_ints(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, int):
        return (value,)
    if not isinstance(value, list | tuple):
        return ()
    return tuple(int(item) for item in value)


def _tuple_floats(value: object) -> tuple[float, ...]:
    if value is None:
        return ()
    if isinstance(value, int | float):
        return (float(value),)
    if not isinstance(value, list | tuple):
        return ()
    return tuple(float(item) for item in value)


def _group_by_date(history: Mapping[str, list[Bar]]) -> dict[date, dict[str, Bar]]:
    grouped: dict[date, dict[str, Bar]] = {}
    for symbol, bars in history.items():
        for bar in bars:
            grouped.setdefault(bar.trade_date, {})[symbol] = bar
    return {trade_date: grouped[trade_date] for trade_date in sorted(grouped)}


def _render_daily_json(
    *,
    monitor: MonitorAgent,
    result: AgentLoopResult,
    symbols: tuple[str, ...],
    data_sync_report: DataSyncReport,
    strategy_diagnostics_path: Path,
) -> str:
    payload = json.loads(
        monitor.render_daily_json(
            as_of=result.as_of,
            regime=result.regime,
            targets=list(result.targets),
            risk_decision=result.risk_decision,
            orders=list(result.orders),
            fills=list(result.fills),
            reconcile=result.reconcile,
            strategy_diagnostics=list(result.strategy_diagnostics),
            strategy_diagnostics_path=strategy_diagnostics_path,
        )
    )
    payload["symbols"] = list(symbols)
    payload["manual_orders_count"] = len(result.risk_decision.approved_orders)
    if result.meta_decision is not None:
        payload["meta_decision"] = asdict(result.meta_decision)
    payload["data_sync"] = asdict(data_sync_report)
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def _render_strategy_diagnostics_json(result: AgentLoopResult) -> str:
    payload = {
        "as_of": result.as_of.isoformat(),
        "meta_decision": asdict(result.meta_decision) if result.meta_decision is not None else None,
        "raw_candidate_counts": _raw_candidate_counts(result.strategy_diagnostics),
        "records": [asdict(record) for record in result.strategy_diagnostics],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=_json_default)


def _raw_candidate_counts(records: Sequence[StrategyDiagnosticRecord]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = counts.setdefault(record.strategy_id, {"eligible": 0, "selected": 0, "rejected": 0})
        if record.eligible:
            bucket["eligible"] += 1
        else:
            bucket["rejected"] += 1
        if record.selected:
            bucket["selected"] += 1
    return counts


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _write_failed_sync_report(report_dir: Path, sync_report: DataSyncReport) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "data_sync_report.json").write_text(
        json.dumps(asdict(sync_report), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
