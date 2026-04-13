"""Helpers for reading daily pipeline artifacts for LLM-side reporting."""

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


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
