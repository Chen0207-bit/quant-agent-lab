"""Robot-facing daily report aggregation helpers."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def build_robot_report(report_dir: Path | str) -> dict[str, object]:
    base = Path(report_dir)
    daily_summary = _load_json(base / "daily_summary.json")
    data_sync = _load_json(base / "data_sync_report.json")
    diagnostics = _load_optional_json(base / "strategy_diagnostics.json") or {}
    universe_snapshot = _load_optional_json(base / "universe_snapshot.json") or {}
    llm_report = _load_optional_json(base / "llm_report.json")
    preflight_validation = _load_optional_json(base / "preflight_validation.json")

    records = _records(diagnostics.get("records"))
    selected_records = [record for record in records if bool(record.get("selected"))]
    rejected_records = [record for record in records if str(record.get("rejection_reason") or "")]
    targets = _records(daily_summary.get("targets"))
    regime_payload = _payload_dict(daily_summary.get("regime"))
    regime_health = _payload_dict(daily_summary.get("regime_health"))
    regime_weights = _payload_dict(regime_health.get("weights") or regime_payload.get("weights"))

    payload: dict[str, object] = {
        "as_of": str(daily_summary.get("as_of", "")),
        "report_dir": str(base),
        "regime": str(regime_payload.get("regime", "unknown")),
        "regime_reason": str(regime_payload.get("reason", "")),
        "regime_weights": {str(key): float(value) for key, value in regime_weights.items() if isinstance(value, int | float)},
        "risk_action": str(daily_summary.get("risk_action", "UNKNOWN")),
        "reconcile": _payload_dict(daily_summary.get("reconcile")),
        "targets_count": len(targets),
        "orders_submitted": len(_payload_list(daily_summary.get("orders"))),
        "raw_candidate_counts": _payload_dict(diagnostics.get("raw_candidate_counts") or daily_summary.get("raw_candidate_counts")),
        "strategy_families": _summarize_families(records, regime_weights),
        "selected_symbols": sorted({str(record.get("symbol", "")) for record in selected_records if record.get("symbol")}),
        "rejected_symbols": sorted({str(record.get("symbol", "")) for record in rejected_records if record.get("symbol")}),
        "top_rejection_reasons": _top_rejection_reasons(rejected_records),
        "llm_status": _llm_status(llm_report),
        "llm_summary": _llm_summary(llm_report),
        "validation_status": _validation_status(preflight_validation),
        "validation_window_start": _string_or_none(preflight_validation, "validation_window_start"),
        "validation_window_end": _string_or_none(preflight_validation, "validation_window_end"),
        "validation_sample_days": _int_or_zero(preflight_validation, "sample_days"),
        "validation_forward_return_horizons": _int_list(preflight_validation.get("forward_return_horizons") if preflight_validation else None),
        "selected_vs_rejected_spread": _payload_dict(preflight_validation.get("selected_vs_rejected_spread") if preflight_validation else None),
        "validation_warnings": _string_list(preflight_validation.get("warnings") if preflight_validation else None),
        "manual_orders_path": str(base / "manual_orders.csv"),
        "daily_summary_path": str(base / "daily_summary.md"),
        "strategy_diagnostics_path": str(base / "strategy_diagnostics.json"),
        "preflight_validation_path": str(base / "preflight_validation.json") if preflight_validation is not None else None,
        "llm_report_json_path": str(base / "llm_report.json") if llm_report is not None else None,
        "construction_notes": _construction_notes(targets),
        "selected_details": _selected_details(selected_records),
        "universe_member_count": len(_payload_dict(universe_snapshot.get("members"))),
        "data_sync": data_sync,
    }
    return payload


def render_robot_report_markdown(payload: dict[str, object]) -> str:
    families = _payload_list(payload.get("strategy_families"))
    family_lines = [
        (
            f"- {item.get('family', 'unknown')}\uff1a"
            f"\u6743\u91cd {float(item.get('regime_weight', 0.0)):.2f}\uff0c"
            f"\u5019\u9009 {int(item.get('eligible', 0))}\uff0c"
            f"\u5165\u9009 {int(item.get('selected', 0))}\uff0c"
            f"\u6dd8\u6c70 {int(item.get('rejected', 0))}"
        )
        for item in families
    ]
    if not family_lines:
        family_lines = ["- \u65e0"]

    selected_lines = [
        (
            f"- {item.get('symbol', '')}\uff5c\u7b56\u7565\u65cf {item.get('family', '')}\uff5c"
            f"\u6392\u540d {_format_rank(item.get('rank'), item.get('universe_size'))}\uff5c"
            f"\u5206\u6570 {_format_score(item.get('score'))}\uff5c"
            f"\u6743\u91cd {float(item.get('target_weight_before_regime', 0.0)):.2%} -> "
            f"{float(item.get('target_weight_after_regime', 0.0)):.2%}"
        )
        for item in _payload_list(payload.get("selected_details"))
    ]
    if not selected_lines:
        selected_lines = ["- \u65e0"]

    rejection_lines = [
        f"- {_rejection_reason_label(str(item.get('reason', '')))}\uff1a{int(item.get('count', 0))} \u53ea{_format_symbols(_string_list(item.get('symbols')))}"
        for item in _payload_list(payload.get("top_rejection_reasons"))
    ]
    if not rejection_lines:
        rejection_lines = ["- \u65e0"]

    note_lines = [f"- {note}" for note in _string_list(payload.get("construction_notes"))]
    if not note_lines:
        note_lines = ["- \u65e0"]

    reconcile = _payload_dict(payload.get("reconcile"))
    lines = [
        f"# \u91cf\u5316\u65e5\u62a5\uff08\u673a\u5668\u4eba\uff09 {payload.get('as_of', '')}",
        "",
        f"- \u65e5\u671f\uff1a{payload.get('as_of', '')}",
        f"- \u5e02\u573a\u72b6\u6001\uff1a{payload.get('regime', 'unknown')}",
        f"- \u72b6\u6001\u539f\u56e0\uff1a{payload.get('regime_reason', '') or '\u65e0'}",
        f"- \u98ce\u63a7\u7ed3\u8bba\uff1a{payload.get('risk_action', 'UNKNOWN')}",
        f"- \u76ee\u6807\u6301\u4ed3\u6570\uff1a{int(payload.get('targets_count', 0))}",
        f"- \u5df2\u63d0\u4ea4\u8ba2\u5355\u6570\uff1a{int(payload.get('orders_submitted', 0))}",
        f"- \u73b0\u91d1\uff1a{float(reconcile.get('cash', 0.0)):.2f}",
        f"- \u603b\u6743\u76ca\uff1a{float(reconcile.get('equity', 0.0)):.2f}",
        f"- \u6d6e\u52a8\u76c8\u4e8f\uff1a{float(reconcile.get('unrealized_pnl', 0.0)):.2f}",
        f"- \u5bf9\u8d26\u4e00\u81f4\uff1a{_yes_no(reconcile.get('is_consistent', False))}",
        "",
        "## \u62a5\u544a\u524d\u7f6e\u9a8c\u8bc1",
        f"- \u72b6\u6001\uff1a{_validation_status_label(str(payload.get('validation_status', 'missing')))}",
        f"- \u6837\u672c\u4ea4\u6613\u65e5\uff1a{int(payload.get('validation_sample_days', 0) or 0)}",
        f"- \u9a8c\u8bc1\u7a97\u53e3\uff1a{payload.get('validation_window_start') or '\u65e0'} -> {payload.get('validation_window_end') or '\u65e0'}",
        f"- 5\u65e5\u9009\u4e2d-\u6dd8\u6c70\u4ef7\u5dee\uff1a{_format_validation_spread(payload.get('selected_vs_rejected_spread'), 5)}",
        f"- \u9a8c\u8bc1\u544a\u8b66\uff1a{_format_warning_summary(_string_list(payload.get('validation_warnings')))}",
        "",
        "## \u7b56\u7565\u6267\u884c\u6982\u89c8",
        *family_lines,
        "",
        "## \u5165\u9009\u6807\u7684",
        *selected_lines,
        "",
        "## \u4e3b\u8981\u6dd8\u6c70\u539f\u56e0",
        *rejection_lines,
        "",
        "## \u7ec4\u5408\u7ea6\u675f\u8bf4\u660e",
        *note_lines,
        "",
        "## \u9879\u76ee\u5185 LLM \u603b\u7ed3",
        f"- \u72b6\u6001\uff1a{_llm_status_label(str(payload.get('llm_status', 'missing')))}",
        f"- \u6458\u8981\uff1a{payload.get('llm_summary', '') or '\u65e0'}",
        "",
        "## \u6587\u4ef6\u8def\u5f84",
        f"- \u62a5\u544a\u76ee\u5f55\uff1a{payload.get('report_dir', '')}",
        f"- \u65e5\u62a5\u6458\u8981\uff1a{payload.get('daily_summary_path', '')}",
        f"- \u7b56\u7565\u8bca\u65ad\uff1a{payload.get('strategy_diagnostics_path', '')}",
        f"- \u4eba\u5de5\u8ba2\u5355\uff1a{payload.get('manual_orders_path', '')}",
    ]
    preflight_validation_path = payload.get("preflight_validation_path")
    if preflight_validation_path:
        lines.append(f"- Validation JSON\uff1a{preflight_validation_path}")
    llm_report_json_path = payload.get("llm_report_json_path")
    if llm_report_json_path:
        lines.append(f"- LLM JSON\uff1a{llm_report_json_path}")
    return "\n".join(lines).rstrip() + "\n"


def _summarize_families(records: list[dict[str, Any]], regime_weights: dict[str, Any]) -> list[dict[str, object]]:
    buckets: dict[str, dict[str, object]] = {}
    for record in records:
        family = str(record.get("family") or "unknown")
        bucket = buckets.setdefault(
            family,
            {
                "family": family,
                "strategy_ids": set(),
                "eligible": 0,
                "selected": 0,
                "rejected": 0,
                "universe_size": 0,
                "regime_weight": 0.0,
            },
        )
        strategy_id = str(record.get("strategy_id") or "")
        if strategy_id:
            strategy_ids = bucket["strategy_ids"]
            assert isinstance(strategy_ids, set)
            strategy_ids.add(strategy_id)
        if bool(record.get("eligible")):
            bucket["eligible"] = int(bucket["eligible"]) + 1
        else:
            bucket["rejected"] = int(bucket["rejected"]) + 1
        if bool(record.get("selected")):
            bucket["selected"] = int(bucket["selected"]) + 1
        bucket["universe_size"] = max(int(bucket["universe_size"]), int(record.get("universe_size") or 0))

    summarized: list[dict[str, object]] = []
    for family in sorted(buckets):
        bucket = buckets[family]
        strategy_ids = sorted(str(item) for item in bucket.pop("strategy_ids", set()))
        weight = 0.0
        for key in [family, *strategy_ids]:
            value = regime_weights.get(key)
            if isinstance(value, int | float):
                weight = float(value)
                break
        bucket["strategy_ids"] = strategy_ids
        bucket["regime_weight"] = weight
        summarized.append(bucket)
    return summarized


def _top_rejection_reasons(records: list[dict[str, Any]]) -> list[dict[str, object]]:
    counts: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "symbols": set()})
    for record in records:
        reason = str(record.get("rejection_reason") or "unknown")
        bucket = counts[reason]
        bucket["count"] = int(bucket["count"]) + 1
        symbol = str(record.get("symbol") or "")
        if symbol:
            symbols = bucket["symbols"]
            assert isinstance(symbols, set)
            symbols.add(symbol)
    return [
        {
            "reason": reason,
            "count": int(payload["count"]),
            "symbols": sorted(str(symbol) for symbol in payload["symbols"]),
        }
        for reason, payload in sorted(counts.items(), key=lambda item: (-int(item[1]["count"]), item[0]))[:5]
    ]


def _construction_notes(targets: list[dict[str, Any]]) -> list[str]:
    notes: set[str] = set()
    for target in targets:
        reason = str(target.get("reason") or "")
        marker = "constraints="
        if marker in reason:
            suffix = reason.split(marker, 1)[1]
            for note in suffix.split(","):
                cleaned = note.strip()
                if cleaned:
                    notes.add(cleaned)
        if "portfolio_constraint_retains_existing_position" in reason:
            notes.add("portfolio_constraint_retains_existing_position")
    return sorted(notes)


def _selected_details(records: list[dict[str, Any]]) -> list[dict[str, object]]:
    details = [
        {
            "symbol": str(record.get("symbol") or ""),
            "family": str(record.get("family") or "unknown"),
            "rank": record.get("rank"),
            "score": record.get("score"),
            "universe_size": int(record.get("universe_size") or 0),
            "target_weight_before_regime": float(record.get("target_weight_before_regime") or 0.0),
            "target_weight_after_regime": float(record.get("target_weight_after_regime") or 0.0),
        }
        for record in records
        if bool(record.get("selected"))
    ]
    return sorted(details, key=lambda item: ((item.get("rank") is None), int(item.get("rank") or 0), -float(item.get("score") or 0.0), str(item.get("symbol") or "")))[:5]


def _llm_status(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "missing"
    return str(payload.get("status") or "missing")


def _llm_summary(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "\u9879\u76ee\u5185 LLM \u603b\u7ed3\u6587\u4ef6\u7f3a\u5931\uff1b\u5982\u9700\u81ea\u7136\u8bed\u8a00\u603b\u7ed3\uff0c\u8bf7\u7531 OpenClaw \u57fa\u4e8e robot_report.json \u5728\u4f1a\u8bdd\u4fa7\u751f\u6210\u3002"
    status = str(payload.get("status") or "missing")
    summary = str(payload.get("summary") or "").strip()
    if status in {"skipped", "disabled"}:
        return "\u9879\u76ee\u5185 LLM \u603b\u7ed3\u672a\u542f\u7528\uff1b\u5982\u9700\u81ea\u7136\u8bed\u8a00\u603b\u7ed3\uff0c\u8bf7\u7531 OpenClaw \u57fa\u4e8e robot_report.json \u5728\u4f1a\u8bdd\u4fa7\u751f\u6210\u3002"
    if status == "error":
        return summary or "\u9879\u76ee\u5185 LLM \u603b\u7ed3\u6267\u884c\u5931\u8d25\u3002"
    return summary


def _validation_status(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "missing"
    return str(payload.get("validation_status") or "missing")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object at {path}")
    return payload


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json(path)


def _records(value: object) -> list[dict[str, Any]]:
    return [item for item in _payload_list(value) if isinstance(item, dict)]


def _payload_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        return []
    return list(value)


def _payload_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [int(item) for item in value if isinstance(item, (int, float))]


def _string_or_none(payload: dict[str, Any] | None, key: str) -> str | None:
    if payload is None:
        return None
    value = payload.get(key)
    return str(value) if value is not None else None


def _int_or_zero(payload: dict[str, Any] | None, key: str) -> int:
    if payload is None:
        return 0
    value = payload.get(key)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _format_score(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}"
    return "n/a"


def _format_rank(rank: object, universe_size: object) -> str:
    if isinstance(rank, int):
        total = int(universe_size or 0)
        if total > 0:
            return f"{rank}/{total}"
        return str(rank)
    return "\u65e0"


def _format_symbols(symbols: list[str]) -> str:
    if not symbols:
        return ""
    return f"\uff08{','.join(symbols)}\uff09"


def _rejection_reason_label(reason: str) -> str:
    labels = {
        "amount_below_min_amount_cny": "\u6210\u4ea4\u989d\u4e0d\u8db3",
        "score_below_min_momentum": "\u52a8\u91cf\u5206\u6570\u4e0d\u8db3",
        "portfolio_constraint_retains_existing_position": "\u7ec4\u5408\u7ea6\u675f\u4fdd\u7559\u539f\u6301\u4ed3",
    }
    return labels.get(reason, reason or "\u672a\u77e5\u539f\u56e0")


def _llm_status_label(status: str) -> str:
    labels = {
        "success": "\u5df2\u5b8c\u6210",
        "skipped": "\u5df2\u8df3\u8fc7",
        "disabled": "\u672a\u542f\u7528",
        "missing": "\u7f3a\u5931",
        "error": "\u5931\u8d25",
    }
    return labels.get(status, status or "\u672a\u77e5")


def _validation_status_label(status: str) -> str:
    labels = {
        "pass": "\u901a\u8fc7",
        "warn": "\u9884\u8b66",
        "insufficient_data": "\u6837\u672c\u4e0d\u8db3",
        "missing": "\u7f3a\u5931",
    }
    return labels.get(status, status or "\u672a\u77e5")


def _format_validation_spread(value: object, preferred_horizon: int) -> str:
    if not isinstance(value, dict):
        return "n/a"
    metric = value.get(str(preferred_horizon)) or value.get(preferred_horizon)
    if not isinstance(metric, dict):
        return "n/a"
    spread = metric.get("spread")
    if isinstance(spread, (int, float)):
        return f"{float(spread):.2%}"
    return "n/a"


def _format_warning_summary(warnings: list[str]) -> str:
    if not warnings:
        return "\u65e0"
    return "; ".join(warnings)


def _yes_no(value: object) -> str:
    return "\u662f" if bool(value) else "\u5426"
