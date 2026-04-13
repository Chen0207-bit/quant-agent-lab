"""Prompt builders for read-only LLM agents."""

from __future__ import annotations

import json

from quant_system.llm.artifacts import ReportArtifacts, ResearchArtifacts


REPORT_SYSTEM_PROMPT = """You are a read-only quant operations assistant.
Explain the paper-trading report, summarize regime and risk outcomes, and call out anomalies.
You must not propose orders, target positions, risk overrides, or configuration edits.
Keep the output suitable for audit logging."""

RESEARCH_SYSTEM_PROMPT = """You are a read-only quant research assistant.
Review offline strategy research outputs and propose follow-up experiments.
You must not edit code, modify configs, generate orders, override risk, or recommend live execution.
Return concise research guidance suitable for audit logging."""


def build_daily_report_review_prompt(artifacts: ReportArtifacts) -> tuple[str, str]:
    payload = {
        "as_of": artifacts.daily_summary_json.get("as_of"),
        "regime": artifacts.daily_summary_json.get("regime"),
        "regime_health": artifacts.daily_summary_json.get("regime_health"),
        "meta_decision": artifacts.daily_summary_json.get("meta_decision"),
        "risk_action": artifacts.daily_summary_json.get("risk_action"),
        "rejections": artifacts.daily_summary_json.get("rejections"),
        "raw_candidate_counts": artifacts.daily_summary_json.get("raw_candidate_counts"),
        "data_sync": artifacts.data_sync_json,
        "strategy_diagnostics": artifacts.strategy_diagnostics_json,
    }
    user_prompt = (
        "Review the following daily paper-trading artifacts and produce a concise operator summary.\n\n"
        + json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
    )
    return REPORT_SYSTEM_PROMPT, user_prompt


def build_strategy_research_prompt(artifacts: ResearchArtifacts) -> tuple[str, str]:
    user_prompt = (
        "Review the following offline strategy research payload and respond with audit-safe research guidance.\n"
        "Use optional tags 'EXPERIMENT:' for follow-up ideas and 'PROMOTION:' for the promotion call.\n\n"
        + json.dumps(artifacts.to_payload(), ensure_ascii=True, indent=2, sort_keys=True)
    )
    return RESEARCH_SYSTEM_PROMPT, user_prompt
