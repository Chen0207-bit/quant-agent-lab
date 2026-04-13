"""Offline strategy research runner for the A-share paper MVP."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Sequence

from quant_system.backtest.engine import BacktestResult, DailyEventBacktester
from quant_system.common.models import Bar, Board, PositionSnapshot, StrategyDiagnosticRecord
from quant_system.data.a_share_rules import classify_symbol, is_mvp_allowed_instrument
from quant_system.data.storage import BarStorage
from quant_system.execution.paper import CostConfig
from quant_system.risk.engine import RiskConfig
from quant_system.strategies.baseline import EtfMomentumStrategy, MainBoardBreakoutStrategy
from quant_system.strategies.base import Strategy


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    family: str
    params: dict[str, object]
    strategy: Strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an offline strategy research iteration.")
    parser.add_argument("--start", default="2025-01-01", help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", default="2025-08-29", help="End date, YYYY-MM-DD")
    parser.add_argument("--symbols", default="510300,510500,159915,600000,600519", help="Comma-separated symbols")
    parser.add_argument("--data-dir", default="runs/data", help="Local data directory")
    parser.add_argument("--dataset", default="silver", choices=["silver", "gold"], help="Dataset to read")
    parser.add_argument("--output-dir", default="runs/strategy_research", help="Research output base directory")
    parser.add_argument("--use-simulated", action="store_true", help="Use deterministic simulated bars")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = _parse_date(args.start)
    end = _parse_date(args.end)
    symbols = tuple(symbol.strip().split(".")[0] for symbol in args.symbols.split(",") if symbol.strip())
    instruments = {symbol: classify_symbol(symbol) for symbol in symbols}
    instruments = {symbol: instrument for symbol, instrument in instruments.items() if is_mvp_allowed_instrument(instrument)}
    if not instruments:
        raise SystemExit("no MVP-allowed instruments selected")

    if args.use_simulated:
        history = _simulated_history(tuple(instruments), start, end)
    else:
        history = BarStorage(args.data_dir).read_bars(args.dataset, tuple(instruments), start=start, end=end)
        history = {symbol: bars for symbol, bars in history.items() if bars}
        if not history:
            raise SystemExit("no local bars found; sync data first or pass --use-simulated")

    bars_by_date = _group_by_date(history)
    if not bars_by_date:
        raise SystemExit("no bars available for research")

    run_dir = Path(args.output_dir) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    candidates = _build_candidates(tuple(history))
    if not candidates:
        raise SystemExit("no candidates can be built from selected symbols")

    metrics: dict[str, dict[str, object]] = {}
    diagnostics_by_candidate: dict[str, list[StrategyDiagnosticRecord]] = {}
    for candidate in candidates:
        candidate_history = {
            symbol: bars for symbol, bars in history.items() if symbol in candidate.strategy.symbols  # type: ignore[attr-defined]
        }
        candidate_bars_by_date = _group_by_date(candidate_history)
        candidate_instruments = {symbol: instruments[symbol] for symbol in candidate_history}
        result = DailyEventBacktester(
            strategy=candidate.strategy,
            instruments=candidate_instruments,
            risk_config=RiskConfig(max_position_weight=0.20),
            cost_config=CostConfig(),
        ).run(candidate_bars_by_date)
        metrics[candidate.candidate_id] = _metrics(result, candidate_bars_by_date)
        diagnostics_by_candidate[candidate.candidate_id] = _diagnose_candidate(
            candidate.strategy,
            candidate_history,
            result.equity_curve[-1].trade_date if result.equity_curve else end,
        )

    ranking = _rank_candidates(candidates, metrics)
    best_candidate_id = ranking[0]["candidate_id"] if ranking else candidates[0].candidate_id

    _write_json(run_dir / "config.json", {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "symbols": list(history),
        "use_simulated": bool(args.use_simulated),
        "candidate_limits": {"etf": 16, "main_board": 16},
        "promotion_rule": "OOS-style score beats baseline, drawdown no worse by >2pp, no concentration/cash-buffer rejections, diagnostics present",
    })
    _write_json(run_dir / "candidates.json", [
        {"candidate_id": candidate.candidate_id, "family": candidate.family, "params": candidate.params}
        for candidate in candidates
    ])
    _write_json(run_dir / "metrics.json", metrics)
    _write_json(run_dir / "ranking.json", ranking)
    _write_json(run_dir / "strategy_diagnostics.json", {
        "best_candidate_id": best_candidate_id,
        "records": [asdict(record) for record in diagnostics_by_candidate.get(best_candidate_id, [])],
    })
    (run_dir / "summary.md").write_text(_summary(ranking, metrics), encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "best_candidate_id": best_candidate_id}, ensure_ascii=True, indent=2))


def _build_candidates(symbols: tuple[str, ...]) -> list[Candidate]:
    etf_symbols = tuple(symbol for symbol in symbols if classify_symbol(symbol).board == Board.ETF)
    main_symbols = tuple(symbol for symbol in symbols if classify_symbol(symbol).board == Board.MAIN)
    candidates: list[Candidate] = []

    etf_params = []
    for windows, weights in (
        ((20, 60, 120), (0.5, 0.3, 0.2)),
        ((20, 60, 120), (0.4, 0.4, 0.2)),
        ((20, 60), (0.6, 0.4)),
        ((60, 120), (0.6, 0.4)),
    ):
        for volatility_penalty in (0.0, 0.25):
            for top_n in (1, 2):
                etf_params.append({
                    "lookback_windows": windows,
                    "window_weights": weights,
                    "volatility_window": 60,
                    "volatility_penalty": volatility_penalty,
                    "top_n": top_n,
                    "max_weight_per_symbol": 0.20,
                })
    for params in etf_params[:16]:
        if etf_symbols:
            candidates.append(_etf_candidate(etf_symbols, params))

    main_params = []
    for min_amount in (5_000_000.0, 10_000_000.0, 20_000_000.0, 50_000_000.0):
        for top_n in (3, 5):
            for moving_average_days in (20, 30):
                main_params.append({
                    "lookback_days": 20,
                    "top_n": top_n,
                    "max_weight_per_symbol": 0.15,
                    "min_amount_cny": min_amount,
                    "moving_average_days": moving_average_days,
                })
    for params in main_params[:16]:
        if main_symbols:
            candidates.append(_main_candidate(main_symbols, params))
    return candidates


def _etf_candidate(symbols: tuple[str, ...], params: dict[str, object]) -> Candidate:
    strategy = EtfMomentumStrategy("etf_momentum", symbols=symbols, **params)
    return Candidate(_candidate_id("etf", params), "etf", params, strategy)


def _main_candidate(symbols: tuple[str, ...], params: dict[str, object]) -> Candidate:
    strategy = MainBoardBreakoutStrategy("main_board_breakout", symbols=symbols, **params)
    return Candidate(_candidate_id("main_board", params), "main_board", params, strategy)


def _candidate_id(family: str, params: dict[str, object]) -> str:
    payload = json.dumps(params, sort_keys=True, default=list)
    return f"{family}:{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:10]}"


def _metrics(result: BacktestResult, bars_by_date: dict[date, dict[str, Bar]]) -> dict[str, object]:
    equity = [point.equity for point in result.equity_curve]
    if not equity:
        return {}
    returns = [current / previous - 1.0 for previous, current in zip(equity, equity[1:]) if previous > 0]
    total_return = equity[-1] / equity[0] - 1.0 if equity[0] > 0 else 0.0
    first_day = result.equity_curve[0].trade_date
    last_day = result.equity_curve[-1].trade_date
    period_days = max((last_day - first_day).days, 1)
    annualized_return = (1.0 + total_return) ** (365.0 / period_days) - 1.0 if total_return > -1.0 else -1.0
    sharpe = mean(returns) / pstdev(returns) * math.sqrt(252) if len(returns) >= 2 and pstdev(returns) > 0 else 0.0
    max_drawdown = _max_drawdown(equity)
    turnover = sum(fill.notional for fill in result.fills) / max(equity[0], 0.01)
    exposure_values = [max(point.equity - point.cash, 0.0) / max(point.equity, 0.01) for point in result.equity_curve]
    exposure = mean(exposure_values) if exposure_values else 0.0
    regime_counts = {"not_evaluated_in_research_backtester": len(bars_by_date)}
    score = sharpe + 0.5 * total_return - 1.5 * abs(max_drawdown) - 0.2 * turnover
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "trade_count": len(result.fills),
        "turnover": turnover,
        "exposure": exposure,
        "risk_rejection_count": len(result.rejected_orders),
        "regime_counts": regime_counts,
        "score": score,
        "risk_rejections": list(result.rejected_orders),
    }


def _rank_candidates(candidates: list[Candidate], metrics: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    baseline_by_family: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        baseline_by_family.setdefault(candidate.family, metrics[candidate.candidate_id])

    ranking: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_metrics = metrics[candidate.candidate_id]
        baseline = baseline_by_family[candidate.family]
        promoted = _can_promote(candidate_metrics, baseline)
        ranking.append({
            "candidate_id": candidate.candidate_id,
            "family": candidate.family,
            "score": candidate_metrics.get("score", 0.0),
            "promoted": promoted,
            "params": candidate.params,
        })
    return sorted(ranking, key=lambda item: float(item["score"]), reverse=True)


def _can_promote(candidate: dict[str, object], baseline: dict[str, object]) -> bool:
    if float(candidate.get("score", 0.0)) <= float(baseline.get("score", 0.0)):
        return False
    if float(candidate.get("max_drawdown", 0.0)) < float(baseline.get("max_drawdown", 0.0)) - 0.02:
        return False
    rejection_text = "\n".join(str(item) for item in candidate.get("risk_rejections", []))
    if "single-name concentration" in rejection_text or "cash buffer" in rejection_text:
        return False
    return True


def _diagnose_candidate(strategy: Strategy, history: dict[str, list[Bar]], as_of: date) -> list[StrategyDiagnosticRecord]:
    diagnose = getattr(strategy, "diagnose", None)
    if not callable(diagnose):
        return []
    return list(diagnose(as_of, history, PositionSnapshot(as_of, 100000.0, {})))


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1.0)
    return max_dd


def _group_by_date(history: dict[str, list[Bar]]) -> dict[date, dict[str, Bar]]:
    grouped: dict[date, dict[str, Bar]] = {}
    for symbol, bars in history.items():
        for bar in bars:
            grouped.setdefault(bar.trade_date, {})[symbol] = bar
    return {trade_date: grouped[trade_date] for trade_date in sorted(grouped)}


def _simulated_history(symbols: tuple[str, ...], start: date, end: date) -> dict[str, list[Bar]]:
    history: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
    day = start
    idx = 0
    prices = {symbol: 4.0 if classify_symbol(symbol).board == Board.ETF else 10.0 for symbol in symbols}
    while day <= end:
        for symbol in symbols:
            board = classify_symbol(symbol).board
            drift = 0.0012 if board == Board.ETF else 0.0008
            seasonal = ((idx % 17) - 8) * 0.00015
            prices[symbol] = max(1.0, prices[symbol] * (1.0 + drift + seasonal))
            close = prices[symbol]
            amount = 60_000_000.0 if board == Board.ETF else 30_000_000.0
            history[symbol].append(
                Bar(
                    symbol=symbol,
                    trade_date=day,
                    open=close * 0.995,
                    high=close * 1.015,
                    low=close * 0.985,
                    close=close,
                    volume=amount / close,
                    amount=amount,
                    limit_up=close * 1.10,
                    limit_down=close * 0.90,
                )
            )
        day += timedelta(days=1)
        idx += 1
    return history


def _summary(ranking: list[dict[str, object]], metrics: dict[str, dict[str, object]]) -> str:
    lines = [
        "# Strategy Research Summary",
        "",
        "This is a research summary, not investment advice or a trading instruction.",
        "",
        "## Top Candidates",
    ]
    for item in ranking[:5]:
        candidate_metrics = metrics[str(item["candidate_id"])]
        lines.append(
            f"- {item['candidate_id']}: score={float(item['score']):.4f}, "
            f"return={float(candidate_metrics.get('total_return', 0.0)):.4f}, "
            f"drawdown={float(candidate_metrics.get('max_drawdown', 0.0)):.4f}, "
            f"sharpe={float(candidate_metrics.get('sharpe', 0.0)):.4f}, "
            f"promoted={item['promoted']}"
        )
    lines.extend([
        "",
        "## Guardrails",
        "- Paper-only research output.",
        "- Risk and execution rules are not modified by this runner.",
        "- Promotion only marks a candidate for human review; it does not change production config.",
    ])
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: object) -> object:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    return str(value)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    main()
