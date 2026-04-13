"""Offline data quality smoke entrypoint."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from quant_system.common.models import Bar
from quant_system.data.quality import validate_bars


def main() -> None:
    bars = [
        Bar("510300", date(2025, 1, 2), open=4.0, high=4.1, low=3.9, close=4.0, volume=1000000),
        Bar("600000", date(2025, 1, 2), open=10.0, high=10.2, low=9.8, close=10.1, volume=2000000),
    ]
    report = validate_bars(bars)
    print(json.dumps({"component": "data_sync_smoke", "passed": report.passed, "issues": [asdict(issue) for issue in report.issues]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
