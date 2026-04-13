"""Data quality checks for daily bars."""

from __future__ import annotations

from dataclasses import dataclass

from quant_system.common.models import Bar


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    symbol: str
    trade_date: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    issues: tuple[DataQualityIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "ERROR" for issue in self.issues)


def validate_bars(bars: list[Bar]) -> DataQualityReport:
    seen: set[tuple[str, str]] = set()
    issues: list[DataQualityIssue] = []
    for bar in bars:
        key = (bar.symbol, bar.trade_date.isoformat())
        if key in seen:
            issues.append(_issue(bar, "ERROR", "duplicate bar"))
        seen.add(key)
        if not bar.is_valid_ohlc():
            issues.append(_issue(bar, "ERROR", "invalid ohlc values"))
        if bar.volume < 0:
            issues.append(_issue(bar, "ERROR", "negative volume"))
        if bar.volume == 0 and not bar.is_suspended:
            issues.append(_issue(bar, "WARN", "zero volume on non-suspended bar"))
        if bar.pre_close is not None and bar.pre_close <= 0:
            issues.append(_issue(bar, "ERROR", "non-positive pre_close"))
    return DataQualityReport(tuple(issues))


def _issue(bar: Bar, severity: str, message: str) -> DataQualityIssue:
    return DataQualityIssue(bar.symbol, bar.trade_date.isoformat(), severity, message)
