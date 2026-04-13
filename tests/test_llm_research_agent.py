import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any

from quant_system.llm import DisabledLLMClient, LLMResearchAgent, load_research_artifacts


EXPECTED_RESEARCH_JSON_KEYS = {
    "agent_name",
    "status",
    "provider",
    "model",
    "prompt_hash",
    "input_artifacts",
    "best_candidate_id",
    "research_summary",
    "recommended_experiments",
    "promotion_assessment",
    "metadata",
}


class LLMResearchAgentTest(unittest.TestCase):
    def test_disabled_llm_writes_research_report_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_research_inputs(run_dir)

            artifacts = load_research_artifacts(run_dir)
            record = LLMResearchAgent(
                client=DisabledLLMClient(),
                enabled=False,
                provider="disabled",
                model="disabled",
            ).propose_experiments(report_dir=run_dir, strategy_payload=artifacts.to_payload())

            self.assertEqual(record.as_of, date(2025, 1, 31))
            self.assertEqual(record.status, "skipped")
            self.assertTrue((run_dir / "llm_research.md").exists())
            self.assertTrue((run_dir / "llm_research.json").exists())
            self.assertTrue((run_dir / "llm_audit.jsonl").exists())
            payload = json.loads((run_dir / "llm_research.json").read_text(encoding="utf-8"))
            self.assertEqual(set(payload), EXPECTED_RESEARCH_JSON_KEYS)
            self.assertEqual(payload["agent_name"], "LLMResearchAgent")
            self.assertEqual(payload["status"], "skipped")
            self.assertIn("promotion_assessment", payload)
            self.assertIn("recommended_experiments", payload)
            audit_lines = (run_dir / "llm_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(audit_lines), 1)
            audit_payload = json.loads(audit_lines[0])
            self.assertEqual(audit_payload["status"], "skipped")
            self.assertEqual(audit_payload["agent_name"], "LLMResearchAgent")

    def test_client_failure_writes_error_artifacts_without_mutating_research_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_research_inputs(run_dir)
            summary_before = (run_dir / "summary.md").read_text(encoding="utf-8")
            metrics_before = (run_dir / "metrics.json").read_text(encoding="utf-8")

            artifacts = load_research_artifacts(run_dir)
            record = LLMResearchAgent(
                client=_FailingLLMClient(),
                enabled=True,
                provider="test-provider",
                model="test-model",
            ).propose_experiments(report_dir=run_dir, strategy_payload=artifacts.to_payload())

            self.assertEqual(record.status, "error")
            self.assertEqual(record.error, "provider unavailable")
            self.assertEqual((run_dir / "summary.md").read_text(encoding="utf-8"), summary_before)
            self.assertEqual((run_dir / "metrics.json").read_text(encoding="utf-8"), metrics_before)
            payload = json.loads((run_dir / "llm_research.json").read_text(encoding="utf-8"))
            self.assertEqual(set(payload), EXPECTED_RESEARCH_JSON_KEYS)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["provider"], "test-provider")
            self.assertEqual(payload["model"], "test-model")
            self.assertEqual(payload["metadata"]["reason"], "client_exception")
            self.assertEqual(payload["metadata"]["error"], "provider unavailable")
            self.assertEqual(payload["recommended_experiments"], [])
            self.assertFalse(payload["promotion_assessment"]["recommended"])
            audit_lines = (run_dir / "llm_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(audit_lines), 1)
            audit_payload = json.loads(audit_lines[0])
            self.assertEqual(audit_payload["status"], "error")
            self.assertEqual(audit_payload["error"], "provider unavailable")


def _write_research_inputs(run_dir: Path) -> None:
    _write_json(run_dir / "config.json", {
        "start": "2025-01-01",
        "end": "2025-01-31",
        "promotion_rule": "score beats baseline",
    })
    _write_json(run_dir / "candidates.json", [
        {"candidate_id": "etf:abc", "family": "etf", "params": {"top_n": 1}},
    ])
    _write_json(run_dir / "metrics.json", {
        "etf:abc": {"score": 1.2, "total_return": 0.1},
    })
    _write_json(run_dir / "ranking.json", [
        {"candidate_id": "etf:abc", "family": "etf", "score": 1.2, "promoted": True},
    ])
    _write_json(run_dir / "strategy_diagnostics.json", {
        "best_candidate_id": "etf:abc",
        "records": [{"as_of": "2025-01-31", "symbol": "510300"}],
    })
    (run_dir / "summary.md").write_text("# Strategy Research Summary\n", encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _FailingLLMClient:
    def generate(self, request: Any) -> Any:
        raise RuntimeError("provider unavailable")


if __name__ == "__main__":
    unittest.main()
