import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from quant_system.llm import DisabledLLMClient, LLMReportAgent, load_report_artifacts


class LLMReportAgentTest(unittest.TestCase):
    def test_disabled_llm_writes_report_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            (report_dir / "daily_summary.md").write_text("# Daily Agent Summary: 2025-01-08\n", encoding="utf-8")
            (report_dir / "daily_summary.json").write_text(
                json.dumps(
                    {
                        "as_of": "2025-01-08",
                        "regime": {"regime": "uncertain", "confidence": 0.2, "weights": {}, "reason": "test"},
                        "regime_health": {"mode": "defensive", "weights": {}},
                        "risk_action": "APPROVE",
                        "rejections": [],
                        "raw_candidate_counts": {},
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            (report_dir / "data_sync_report.json").write_text(
                json.dumps(
                    {
                        "symbols_requested": ["510300"],
                        "symbols_succeeded": ["510300"],
                        "symbols_failed": [],
                        "bars_written": 5,
                        "quality_passed": True,
                        "issues": [],
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            artifacts = load_report_artifacts(report_dir)
            record = LLMReportAgent(
                client=DisabledLLMClient(),
                enabled=False,
                provider="disabled",
                model="disabled",
            ).review_daily_report(artifacts, run_id="llm_report_test")

            self.assertEqual(record.as_of, date(2025, 1, 8))
            self.assertEqual(record.status, "skipped")
            self.assertTrue((report_dir / "llm_report.md").exists())
            self.assertTrue((report_dir / "llm_report.json").exists())
            self.assertTrue((report_dir / "llm_audit.jsonl").exists())
            payload = json.loads((report_dir / "llm_report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "skipped")
            self.assertEqual(payload["agent_name"], "LLMReportAgent")
            audit_lines = (report_dir / "llm_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(audit_lines), 1)


if __name__ == "__main__":
    unittest.main()
