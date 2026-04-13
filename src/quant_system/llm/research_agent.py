"""Read-only research assistant scaffolding for future LLM integration."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from quant_system.common.ids import new_run_id
from quant_system.llm.audit import LLMAuditRecord, append_audit_record, build_prompt_hash
from quant_system.llm.base import LLMClient, LLMRequest


class LLMResearchAgent:
    def __init__(self, *, client: LLMClient, provider: str, model: str) -> None:
        self.client = client
        self.provider = provider
        self.model = model

    def propose_experiments(self, *, report_dir: Path, strategy_payload: dict[str, object]) -> LLMAuditRecord:
        system_prompt = (
            "You are a read-only quant research assistant. "
            "Propose experiments and diagnostics without editing code or producing orders."
        )
        user_prompt = json.dumps(strategy_payload, ensure_ascii=True, indent=2, sort_keys=True)
        response = self.client.generate(LLMRequest(system_prompt=system_prompt, user_prompt=user_prompt))
        prompt_hash = build_prompt_hash(system_prompt, user_prompt)
        output_path = report_dir / "llm_research.json"
        output_path.write_text(
            json.dumps(
                {
                    "status": response.status,
                    "provider": response.provider,
                    "model": response.model,
                    "summary": response.content,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        as_of_raw = strategy_payload.get("as_of")
        as_of = date.fromisoformat(str(as_of_raw)) if as_of_raw is not None else date.today()
        record = LLMAuditRecord(
            run_id=new_run_id("llm_research"),
            as_of=as_of,
            agent_name="LLMResearchAgent",
            provider=response.provider,
            model=response.model,
            prompt_hash=prompt_hash,
            input_artifacts=(str(report_dir),),
            output_path=str(output_path),
            status=response.status,
        )
        append_audit_record(report_dir / "llm_audit.jsonl", record)
        return record
