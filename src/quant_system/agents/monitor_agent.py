"""Monitoring and reporting agent."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from quant_system.agents.regime_agent import RegimeState
from quant_system.common.models import (
    Fill,
    Order,
    OrderIntent,
    ReconcileReport,
    RiskDecision,
    StrategyDiagnosticRecord,
    TargetPosition,
)
from quant_system.execution.manual_export import export_manual_orders


class MonitorAgent:
    def render_daily_summary(
        self,
        *,
        as_of: date,
        regime: RegimeState,
        targets: list[TargetPosition],
        risk_decision: RiskDecision,
        orders: list[Order],
        fills: list[Fill],
        reconcile: ReconcileReport,
        strategy_diagnostics: list[StrategyDiagnosticRecord] | None = None,
    ) -> str:
        raw_counts = _raw_candidate_counts(strategy_diagnostics or [])
        lines = [
            f"# Daily Agent Summary: {as_of.isoformat()}",
            "",
            f"- Regime: {regime.regime} ({regime.confidence:.2f})",
            f"- Regime reason: {regime.reason}",
            f"- Regime mode: {_regime_mode(regime)}",
            f"- Regime weights: {_format_weights(regime.weights)}",
            f"- Raw strategy candidates: {_format_candidate_counts(raw_counts)}",
            f"- Targets: {len(targets)}",
            f"- Risk action: {risk_decision.action.value}",
            f"- Risk rejections: {len(risk_decision.rejections)}",
            f"- Orders submitted: {len(orders)}",
            f"- Fills total: {len(fills)}",
            f"- Reconcile consistent: {reconcile.is_consistent}",
            f"- Cash: {reconcile.cash:.2f}",
        ]
        if risk_decision.rejections:
            lines.append("")
            lines.append("## Rejections")
            for rejection in risk_decision.rejections:
                lines.append(f"- {rejection.symbol}: {rejection.reason}")
        return "\n".join(lines)

    def render_daily_json(
        self,
        *,
        as_of: date,
        regime: RegimeState,
        targets: list[TargetPosition],
        risk_decision: RiskDecision,
        orders: list[Order],
        fills: list[Fill],
        reconcile: ReconcileReport,
        strategy_diagnostics: list[StrategyDiagnosticRecord] | None = None,
        strategy_diagnostics_path: Path | None = None,
    ) -> str:
        diagnostics = strategy_diagnostics or []
        payload = {
            "as_of": as_of.isoformat(),
            "regime": asdict(regime),
            "regime_health": {
                "mode": _regime_mode(regime),
                "weights": dict(regime.weights),
            },
            "targets": [asdict(target) for target in targets],
            "raw_candidate_counts": _raw_candidate_counts(diagnostics),
            "strategy_diagnostics_path": str(strategy_diagnostics_path) if strategy_diagnostics_path else None,
            "risk_action": risk_decision.action.value,
            "rejections": [asdict(rejection) for rejection in risk_decision.rejections],
            "orders": [order.order_id for order in orders],
            "fills": [fill.fill_id for fill in fills],
            "reconcile": asdict(reconcile),
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=_json_default)

    def write_daily_outputs(
        self,
        *,
        report_dir: Path,
        daily_summary: str,
        daily_summary_json: str,
        manual_orders: list[OrderIntent],
        data_sync_report: object,
        strategy_diagnostics_json: str | None = None,
    ) -> dict[str, Path]:
        report_dir.mkdir(parents=True, exist_ok=True)
        summary_path = report_dir / "daily_summary.md"
        json_path = report_dir / "daily_summary.json"
        manual_orders_path = report_dir / "manual_orders.csv"
        data_sync_path = report_dir / "data_sync_report.json"
        diagnostics_path = report_dir / "strategy_diagnostics.json"

        summary_path.write_text(daily_summary + "\n", encoding="utf-8")
        json_path.write_text(daily_summary_json.rstrip() + "\n", encoding="utf-8")
        export_manual_orders(manual_orders_path, manual_orders)
        data_sync_path.write_text(
            json.dumps(
                _as_jsonable(data_sync_report),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        paths = {
            "daily_summary": summary_path,
            "daily_summary_json": json_path,
            "manual_orders": manual_orders_path,
            "data_sync_report": data_sync_path,
        }
        if strategy_diagnostics_json is not None:
            diagnostics_path.write_text(strategy_diagnostics_json.rstrip() + "\n", encoding="utf-8")
            paths["strategy_diagnostics"] = diagnostics_path
        return paths


def _regime_mode(regime: RegimeState) -> str:
    if regime.regime == "crisis":
        return "crisis"
    if regime.regime == "uncertain":
        return "defensive"
    return "normal"


def _format_weights(weights: dict[str, float]) -> str:
    return ", ".join(f"{key}={value:.2f}" for key, value in sorted(weights.items()))


def _raw_candidate_counts(records: list[StrategyDiagnosticRecord]) -> dict[str, dict[str, int]]:
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


def _format_candidate_counts(counts: dict[str, dict[str, int]]) -> str:
    if not counts:
        return "none"
    return ", ".join(
        f"{strategy_id}(eligible={value['eligible']}, selected={value['selected']}, rejected={value['rejected']})"
        for strategy_id, value in sorted(counts.items())
    )


def _json_default(value: object) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)


def _as_jsonable(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value
