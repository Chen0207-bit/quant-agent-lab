import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from quant_system.llm import DisabledLLMClient, LLMResearchAgent, load_research_artifacts


class LLMResearchAgentTest(unittest.TestCase):
    def test_disabled_llm_writes_research_report_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
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
            self.assertEqual(payload["agent_name"], "LLMResearchAgent")
            self.assertEqual(payload["status"], "skipped")
            self.assertIn("promotion_assessment", payload)
            self.assertIn("recommended_experiments", payload)
            audit_lines = (run_dir / "llm_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(audit_lines), 1)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
