"""Minimal health check entrypoint."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def main() -> None:
    print(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "status": "ok", "component": "quant-a-share"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
