"""Read-only research assistant for offline strategy research artifacts."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from quant_system.common.ids import new_run_id
from quant_system.llm.artifacts import ResearchArtifacts
from quant_system.llm.audit import LLMAuditRecord, append_audit_record, build_prompt_hash
from quant_system.llm.base import LLMClient, LLMRequest, LLMResponse
from quant_system.llm.prompts import build_strategy_research_prompt


class LLMResearchAgent:
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

    def propose_experiments(self, *, report_dir: Path, strategy_payload: dict[str, object]) -> LLMAuditRecord:
        artifacts = _artifacts_from_payload(report_dir, strategy_payload)
        system_prompt, user_prompt = build_strategy_research_prompt(artifacts)
        prompt_hash = build_prompt_hash(system_prompt, user_prompt)
        request = LLMRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata={
                "as_of": artifacts.as_of.isoformat(),
                "input_artifacts": artifacts.input_artifacts,
                "enabled": self.enabled,
            },
        )
        try:
            response = self.client.generate(request)
        except Exception as exc:
            response = LLMResponse(
                status="error",
                content=(
                    "LLM research review failed before completion: "
                    f"{type(exc).__name__}: {exc}"
                ),
                provider=self.provider,
                model=self.model,
                metadata={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "reason": "client_exception",
                },
            )
        markdown_path = report_dir / "llm_research.md"
        json_path = report_dir / "llm_research.json"
        audit_path = report_dir / "llm_audit.jsonl"
        experiments = _extract_experiments(response.content)
        promotion = _extract_promotion_assessment(response.content, response.status)
        markdown_path.write_text(
            _render_markdown(artifacts.as_of.isoformat(), response.content, response.status, response.provider, response.model),
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(
                {
                    "agent_name": "LLMResearchAgent",
                    "status": response.status,
                    "provider": response.provider,
                    "model": response.model,
                    "prompt_hash": prompt_hash,
                    "input_artifacts": list(artifacts.input_artifacts),
                    "best_candidate_id": str(strategy_payload.get("best_candidate_id", "")),
                    "research_summary": response.content,
                    "recommended_experiments": experiments,
                    "promotion_assessment": promotion,
                    "metadata": response.metadata,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        record = LLMAuditRecord(
            run_id=new_run_id("llm_research"),
            as_of=artifacts.as_of,
            agent_name="LLMResearchAgent",
            provider=response.provider,
            model=response.model,
            prompt_hash=prompt_hash,
            input_artifacts=artifacts.input_artifacts,
            output_path=str(json_path),
            recommended_actions=tuple(experiments),
            status=response.status,
            error=response.metadata.get("error") if isinstance(response.metadata, dict) else None,
        )
        append_audit_record(audit_path, record)
        return record


def _artifacts_from_payload(report_dir: Path, strategy_payload: dict[str, object]) -> ResearchArtifacts:
    as_of_raw = strategy_payload.get("as_of")
    if as_of_raw is None:
        raise ValueError("strategy_payload must include as_of")
    as_of = date.fromisoformat(str(as_of_raw))
    return ResearchArtifacts(
        run_dir=report_dir,
        as_of=as_of,
        config_path=report_dir / "config.json",
        candidates_path=report_dir / "candidates.json",
        metrics_path=report_dir / "metrics.json",
        ranking_path=report_dir / "ranking.json",
        strategy_diagnostics_path=report_dir / "strategy_diagnostics.json",
        summary_path=report_dir / "summary.md",
        config_json={"promotion_rule": strategy_payload.get("promotion_rule")},
        candidates_json=_payload_list(strategy_payload.get("candidates")),
        metrics_json={str(strategy_payload.get("best_candidate_id", "")): _payload_dict(strategy_payload.get("best_candidate_metrics"))},
        ranking_json=_payload_list(strategy_payload.get("ranking")),
        strategy_diagnostics_json=_payload_dict(strategy_payload.get("diagnostics")),
        summary_markdown=str(strategy_payload.get("summary_markdown", "")),
    )


def _payload_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _payload_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _render_markdown(as_of: str, content: str, status: str, provider: str, model: str) -> str:
    lines = [
        f"# LLM Research Review: {as_of}",
        "",
        f"- Status: {status}",
        f"- Provider: {provider}",
        f"- Model: {model}",
        "",
        content.strip(),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _extract_experiments(content: str) -> list[str]:
    experiments: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("EXPERIMENT:"):
            experiments.append(stripped.removeprefix("EXPERIMENT:").strip())
    return experiments


def _extract_promotion_assessment(content: str, status: str) -> dict[str, object]:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("PROMOTION:"):
            continue
        raw = stripped.removeprefix("PROMOTION:").strip()
        lowered = raw.lower()
        if lowered.startswith("yes"):
            rationale = raw[3:].lstrip(" :-") or "recommended by LLM research review"
            return {"recommended": True, "rationale": rationale}
        if lowered.startswith("no"):
            rationale = raw[2:].lstrip(" :-") or "not recommended by LLM research review"
            return {"recommended": False, "rationale": rationale}
        return {"recommended": False, "rationale": raw}
    default_rationale = content.strip() or f"LLM research status: {status}"
    return {"recommended": False, "rationale": default_rationale}
