"""Read-only sentiment agent scaffolding for future text features."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from quant_system.common.ids import new_run_id
from quant_system.llm.audit import LLMAuditRecord, append_audit_record, build_prompt_hash
from quant_system.llm.base import LLMClient, LLMRequest


@dataclass(frozen=True, slots=True)
class TextArtifact:
    as_of: date
    source_url: str
    source_time: str
    title: str
    body: str


class LLMSentimentAgent:
    def __init__(self, *, client: LLMClient, provider: str, model: str) -> None:
        self.client = client
        self.provider = provider
        self.model = model

    def extract_features(self, *, text_artifacts: list[TextArtifact], output_dir: Path) -> LLMAuditRecord:
        system_prompt = (
            "You are a read-only sentiment extraction assistant. "
            "Summarize the supplied texts and produce audit-safe research features only."
        )
        user_prompt = json.dumps([
            {
                "as_of": artifact.as_of.isoformat(),
                "source_url": artifact.source_url,
                "source_time": artifact.source_time,
                "title": artifact.title,
                "body": artifact.body,
            }
            for artifact in text_artifacts
        ], ensure_ascii=True, indent=2, sort_keys=True)
        response = self.client.generate(LLMRequest(system_prompt=system_prompt, user_prompt=user_prompt))
        prompt_hash = build_prompt_hash(system_prompt, user_prompt)
        output_path = output_dir / "llm_sentiment.json"
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
        as_of = text_artifacts[0].as_of if text_artifacts else date.today()
        record = LLMAuditRecord(
            run_id=new_run_id("llm_sentiment"),
            as_of=as_of,
            agent_name="LLMSentimentAgent",
            provider=response.provider,
            model=response.model,
            prompt_hash=prompt_hash,
            input_artifacts=tuple(artifact.source_url for artifact in text_artifacts),
            output_path=str(output_path),
            status=response.status,
        )
        append_audit_record(output_dir / "llm_audit.jsonl", record)
        return record
