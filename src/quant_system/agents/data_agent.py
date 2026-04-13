"""Data agent for deterministic daily history preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Sequence

from quant_system.common.models import Bar
from quant_system.data.calendar import TradingCalendar
from quant_system.data.manager import DataManager, DataSyncReport


@dataclass(frozen=True, slots=True)
class DataAgentResult:
    as_of: date
    history_start: date
    symbols: tuple[str, ...]
    history: dict[str, list[Bar]]
    bars_by_date: dict[date, dict[str, Bar]]
    sync_report: DataSyncReport


class DataAgentError(RuntimeError):
    def __init__(self, message: str, sync_report: DataSyncReport | None = None) -> None:
        super().__init__(message)
        self.sync_report = sync_report


class DataAgent:
    """Prepare validated local history for the daily agent loop.

    The agent is deterministic: it only coordinates calendar lookup, data sync,
    local reads, and quality failure propagation.
    """

    def __init__(
        self,
        *,
        manager: DataManager,
        calendar: TradingCalendar,
        dataset: str = "silver",
    ) -> None:
        self.manager = manager
        self.calendar = calendar
        self.dataset = dataset

    def prepare_history(
        self,
        *,
        as_of: date,
        symbols: Sequence[str],
        lookback_days: int,
        start: date | None = None,
    ) -> DataAgentResult:
        selected_symbols = tuple(dict.fromkeys(symbol.strip().split(".")[0] for symbol in symbols if symbol.strip()))
        if not selected_symbols:
            raise DataAgentError("data agent received an empty symbol universe")

        effective_as_of = self.calendar.latest_trading_day(as_of)
        history_start = start or effective_as_of - timedelta(days=max(lookback_days * 4, 90))
        sync_report = self.manager.sync_history(
            selected_symbols,
            history_start,
            effective_as_of,
            dataset=self.dataset,
        )
        if not sync_report.quality_passed:
            raise DataAgentError("data sync failed: " + "; ".join(sync_report.issues), sync_report)

        history = {
            symbol: self.manager.get_history(
                symbol,
                start_date=history_start,
                end_date=effective_as_of,
                dataset=self.dataset,
            )
            for symbol in selected_symbols
        }
        missing = tuple(symbol for symbol, bars in history.items() if not bars)
        if missing:
            raise DataAgentError(f"no local bars after sync for {', '.join(missing)}", sync_report)

        bars_by_date = _group_by_date(history)
        if not bars_by_date:
            raise DataAgentError("no bars available for agent loop", sync_report)

        return DataAgentResult(
            as_of=effective_as_of,
            history_start=history_start,
            symbols=selected_symbols,
            history=history,
            bars_by_date=bars_by_date,
            sync_report=sync_report,
        )


def _group_by_date(history: Mapping[str, list[Bar]]) -> dict[date, dict[str, Bar]]:
    grouped: dict[date, dict[str, Bar]] = {}
    for symbol, bars in history.items():
        for bar in bars:
            grouped.setdefault(bar.trade_date, {})[symbol] = bar
    return {trade_date: grouped[trade_date] for trade_date in sorted(grouped)}

