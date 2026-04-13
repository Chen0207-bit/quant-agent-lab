"""LLM audit record helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMAuditRecord:
    run_id: str
    as_of: date
    agent_name: str
    provider: str
    model: str
    prompt_hash: str
    input_artifacts: tuple[str, ...]
    output_path: str
    recommended_actions: tuple[str, ...] = ()
    accepted_by_human: bool = False
    accepted_by_program: bool = False
    final_decision_reference: str | None = None
    status: str = "skipped"
    error: str | None = None


def build_prompt_hash(system_prompt: str, user_prompt: str) -> str:
    payload = f"{system_prompt}\n---\n{user_prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def append_audit_record(path: Path | str, record: LLMAuditRecord) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = _serialize_record(record)
    if target.exists():
        target.write_text(target.read_text(encoding="utf-8") + line, encoding="utf-8")
        return
    target.write_text(line, encoding="utf-8")


def _serialize_record(record: LLMAuditRecord) -> str:
    return json.dumps(asdict(record), ensure_ascii=True, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)
