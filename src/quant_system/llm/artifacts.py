"""Helpers for reading daily and research artifacts for LLM-side review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ReportArtifacts:
    report_dir: Path
    as_of: date
    daily_summary_path: Path
    daily_summary_json_path: Path
    data_sync_path: Path
    strategy_diagnostics_path: Path | None
    daily_summary_markdown: str
    daily_summary_json: dict[str, Any]
    data_sync_json: dict[str, Any]
    strategy_diagnostics_json: dict[str, Any] | None

    @property
    def input_artifacts(self) -> tuple[str, ...]:
        paths = [
            str(self.daily_summary_path),
            str(self.daily_summary_json_path),
            str(self.data_sync_path),
        ]
        if self.strategy_diagnostics_path is not None:
            paths.append(str(self.strategy_diagnostics_path))
        return tuple(paths)


@dataclass(frozen=True, slots=True)
class ResearchArtifacts:
    run_dir: Path
    as_of: date
    config_path: Path
    candidates_path: Path
    metrics_path: Path
    ranking_path: Path
    strategy_diagnostics_path: Path
    summary_path: Path
    config_json: dict[str, Any]
    candidates_json: list[dict[str, Any]]
    metrics_json: dict[str, dict[str, Any]]
    ranking_json: list[dict[str, Any]]
    strategy_diagnostics_json: dict[str, Any]
    summary_markdown: str

    @property
    def input_artifacts(self) -> tuple[str, ...]:
        return (
            str(self.config_path),
            str(self.candidates_path),
            str(self.metrics_path),
            str(self.ranking_path),
            str(self.strategy_diagnostics_path),
            str(self.summary_path),
        )

    def to_payload(self) -> dict[str, Any]:
        best_candidate_id = str(self.strategy_diagnostics_json.get("best_candidate_id", ""))
        ranking_entry = next(
            (item for item in self.ranking_json if str(item.get("candidate_id", "")) == best_candidate_id),
            {},
        )
        best_metrics = self.metrics_json.get(best_candidate_id, {})
        return {
            "as_of": self.as_of.isoformat(),
            "best_candidate_id": best_candidate_id,
            "promotion_rule": self.config_json.get("promotion_rule"),
            "best_candidate_metrics": best_metrics,
            "best_candidate_ranking": ranking_entry,
            "ranking": self.ranking_json,
            "candidates": self.candidates_json,
            "diagnostics": self.strategy_diagnostics_json,
            "summary_markdown": self.summary_markdown,
        }


def load_report_artifacts(report_dir: Path | str) -> ReportArtifacts:
    base = Path(report_dir)
    summary_path = base / "daily_summary.md"
    summary_json_path = base / "daily_summary.json"
    data_sync_path = base / "data_sync_report.json"
    diagnostics_path = base / "strategy_diagnostics.json"

    summary_json = _load_json(summary_json_path)
    return ReportArtifacts(
        report_dir=base,
        as_of=date.fromisoformat(str(summary_json["as_of"])),
        daily_summary_path=summary_path,
        daily_summary_json_path=summary_json_path,
        data_sync_path=data_sync_path,
        strategy_diagnostics_path=diagnostics_path if diagnostics_path.exists() else None,
        daily_summary_markdown=summary_path.read_text(encoding="utf-8"),
        daily_summary_json=summary_json,
        data_sync_json=_load_json(data_sync_path),
        strategy_diagnostics_json=_load_json(diagnostics_path) if diagnostics_path.exists() else None,
    )


def load_research_artifacts(run_dir: Path | str) -> ResearchArtifacts:
    base = Path(run_dir)
    config_path = base / "config.json"
    candidates_path = base / "candidates.json"
    metrics_path = base / "metrics.json"
    ranking_path = base / "ranking.json"
    diagnostics_path = base / "strategy_diagnostics.json"
    summary_path = base / "summary.md"

    config_json = _load_json(config_path)
    candidates_json = _load_json(candidates_path)
    metrics_json = _load_json(metrics_path)
    ranking_json = _load_json(ranking_path)
    diagnostics_json = _load_json(diagnostics_path)
    as_of = _resolve_research_as_of(config_json, diagnostics_json)
    return ResearchArtifacts(
        run_dir=base,
        as_of=as_of,
        config_path=config_path,
        candidates_path=candidates_path,
        metrics_path=metrics_path,
        ranking_path=ranking_path,
        strategy_diagnostics_path=diagnostics_path,
        summary_path=summary_path,
        config_json=config_json,
        candidates_json=_as_list_of_dicts(candidates_json),
        metrics_json=_as_dict_of_dicts(metrics_json),
        ranking_json=_as_list_of_dicts(ranking_json),
        strategy_diagnostics_json=diagnostics_json,
        summary_markdown=summary_path.read_text(encoding="utf-8"),
    )


def _resolve_research_as_of(config_json: dict[str, Any], diagnostics_json: dict[str, Any]) -> date:
    records = diagnostics_json.get("records", [])
    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict) and "as_of" in record:
                return date.fromisoformat(str(record["as_of"]))
    if "end" in config_json:
        return date.fromisoformat(str(config_json["end"]))
    raise ValueError("research artifacts do not contain an as_of or end date")


def _as_list_of_dicts(value: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TypeError("expected JSON list")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise TypeError("expected list of JSON objects")
        result.append(item)
    return result


def _as_dict_of_dicts(value: dict[str, Any] | list[Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    result: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            raise TypeError("expected nested JSON objects")
        result[str(key)] = item
    return result


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))
