"""Read-only LLM report agent."""

from __future__ import annotations

import json

from quant_system.common.ids import new_run_id
from quant_system.llm.artifacts import ReportArtifacts
from quant_system.llm.audit import LLMAuditRecord, append_audit_record, build_prompt_hash
from quant_system.llm.base import LLMClient, LLMRequest
from quant_system.llm.prompts import build_daily_report_review_prompt


class LLMReportAgent:
    def __init__(
        self,
        *,
        client: LLMClient,
        enabled: bool,
        provider: str,
        model: str,
    ) -> None:
        self.client = client
        self.enabled = enabled
        self.provider = provider
        self.model = model

    def review_daily_report(
        self,
        report_artifacts: ReportArtifacts,
        *,
        run_id: str | None = None,
    ) -> LLMAuditRecord:
        system_prompt, user_prompt = build_daily_report_review_prompt(report_artifacts)
        prompt_hash = build_prompt_hash(system_prompt, user_prompt)
        response = self.client.generate(
            LLMRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                metadata={
                    "as_of": report_artifacts.as_of.isoformat(),
                    "input_artifacts": report_artifacts.input_artifacts,
                    "enabled": self.enabled,
                },
            )
        )
        output_dir = report_artifacts.report_dir
        markdown_path = output_dir / "llm_report.md"
        json_path = output_dir / "llm_report.json"
        audit_path = output_dir / "llm_audit.jsonl"
        recommended_actions = _extract_recommended_actions(response.content)
        markdown_path.write_text(
            _render_markdown(report_artifacts.as_of.isoformat(), response.content, response.status, response.provider, response.model),
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(
                {
                    "agent_name": "LLMReportAgent",
                    "as_of": report_artifacts.as_of.isoformat(),
                    "status": response.status,
                    "provider": response.provider,
                    "model": response.model,
                    "input_artifacts": list(report_artifacts.input_artifacts),
                    "prompt_hash": prompt_hash,
                    "recommended_actions": recommended_actions,
                    "summary": response.content,
                    "metadata": response.metadata,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        record = LLMAuditRecord(
            run_id=run_id or new_run_id("llm_report"),
            as_of=report_artifacts.as_of,
            agent_name="LLMReportAgent",
            provider=response.provider,
            model=response.model,
            prompt_hash=prompt_hash,
            input_artifacts=report_artifacts.input_artifacts,
            output_path=str(json_path),
            recommended_actions=tuple(recommended_actions),
            status=response.status,
            error=response.metadata.get("error") if isinstance(response.metadata, dict) else None,
        )
        append_audit_record(audit_path, record)
        return record


def _render_markdown(as_of: str, content: str, status: str, provider: str, model: str) -> str:
    lines = [
        f"# LLM Report Review: {as_of}",
        "",
        f"- Status: {status}",
        f"- Provider: {provider}",
        f"- Model: {model}",
        "",
        content.strip(),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _extract_recommended_actions(content: str) -> list[str]:
    actions: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("ACTION:"):
            actions.append(stripped.removeprefix("ACTION:").strip())
    return actions
