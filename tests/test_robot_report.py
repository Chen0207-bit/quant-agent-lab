import json
import tempfile
import unittest
from pathlib import Path

from quant_system.app.robot_report import build_robot_report, render_robot_report_markdown


class RobotReportTest(unittest.TestCase):
    def test_build_robot_report_handles_missing_llm_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            _write_base_report(report_dir)

            payload = build_robot_report(report_dir)

            self.assertEqual(payload["as_of"], "2026-04-13")
            self.assertEqual(payload["llm_status"], "missing")
            self.assertEqual(payload["validation_status"], "pass")
            self.assertIn("robot_report.json", payload["llm_summary"])
            self.assertEqual(payload["selected_symbols"], ["510500"])
            self.assertEqual(payload["rejected_symbols"], ["510300"])
            self.assertEqual(payload["strategy_families"][0]["family"], "etf")
            self.assertEqual(payload["strategy_families"][0]["regime_weight"], 0.7)
            self.assertEqual(payload["top_rejection_reasons"][0]["reason"], "score_below_min_momentum")
            self.assertIn("single_name_cap", payload["construction_notes"])
            markdown = render_robot_report_markdown(payload)
            self.assertIn("LLM", markdown)
            self.assertIn("510500", markdown)
            self.assertIn("Validation", markdown)
            self.assertIn("/tmp/", markdown)

    def test_build_robot_report_uses_llm_error_summary_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            _write_base_report(report_dir)
            (report_dir / "llm_report.json").write_text(
                json.dumps(
                    {
                        "agent_name": "LLMReportAgent",
                        "as_of": "2026-04-13",
                        "status": "error",
                        "provider": "test",
                        "model": "test",
                        "input_artifacts": [],
                        "prompt_hash": "abcd",
                        "recommended_actions": [],
                        "summary": "LLM provider timeout",
                        "metadata": {"error": "timeout"},
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )

            payload = build_robot_report(report_dir)

            self.assertEqual(payload["llm_status"], "error")
            self.assertEqual(payload["llm_summary"], "LLM provider timeout")
            self.assertTrue(str(payload["llm_report_json_path"]).endswith("llm_report.json"))


def _write_base_report(report_dir: Path) -> None:
    (report_dir / "daily_summary.md").write_text("# Daily Agent Summary: 2026-04-13\n", encoding="utf-8")
    (report_dir / "manual_orders.csv").write_text("order_id,strategy_id\n", encoding="utf-8")
    _write_json(
        report_dir / "daily_summary.json",
        {
            "as_of": "2026-04-13",
            "regime": {"regime": "trending", "confidence": 0.7, "reason": "trend strong", "weights": {"etf_momentum": 0.7}},
            "regime_health": {"mode": "normal", "weights": {"etf": 0.7, "etf_momentum": 0.7, "default": 0.2}},
            "risk_action": "APPROVE",
            "orders": ["order-1"],
            "targets": [
                {
                    "symbol": "510500",
                    "target_weight": 0.28,
                    "reason": "family=etf; rank=1; score=0.8123; constraints=single_name_cap"
                }
            ],
            "reconcile": {
                "cash": 105641.98,
                "equity": 105641.98,
                "unrealized_pnl": 0.0,
                "is_consistent": True,
                "reasons": [],
            },
            "raw_candidate_counts": {"etf_momentum": {"eligible": 1, "selected": 1, "rejected": 1}},
            "preflight_validation": {
                "validation_status": "pass",
                "validation_window_start": "2025-01-02",
                "validation_window_end": "2026-04-11",
                "sample_days": 120,
                "forward_return_horizons": [1, 5, 20],
            },
        },
    )
    _write_json(
        report_dir / "data_sync_report.json",
        {
            "symbols_requested": ["510300", "510500"],
            "symbols_succeeded": ["510300", "510500"],
            "symbols_failed": [],
            "bars_written": 632,
            "quality_passed": True,
            "issues": [],
        },
    )
    _write_json(
        report_dir / "preflight_validation.json",
        {
            "as_of": "2026-04-13",
            "validation_window_start": "2025-01-02",
            "validation_window_end": "2026-04-11",
            "sample_days": 120,
            "max_drawdown": -0.03,
            "forward_return_horizons": [1, 5, 20],
            "selected_vs_rejected_spread": {
                "1": {"selected_avg_return": 0.01, "rejected_avg_return": -0.01, "spread": 0.02, "hit_rate": 0.6, "observations": 120},
                "5": {"selected_avg_return": 0.03, "rejected_avg_return": 0.00, "spread": 0.03, "hit_rate": 0.62, "observations": 118},
                "20": {"selected_avg_return": 0.08, "rejected_avg_return": 0.02, "spread": 0.06, "hit_rate": 0.70, "observations": 100}
            },
            "strategy_metrics": [],
            "warnings": [],
            "validation_status": "pass"
        },
    )
    _write_json(
        report_dir / "universe_snapshot.json",
        {
            "as_of": "2026-04-13",
            "members": {
                "510300": {"symbol": "510300", "industry": "ETF", "board": "ETF", "asset_type": "ETF"},
                "510500": {"symbol": "510500", "industry": "ETF", "board": "ETF", "asset_type": "ETF"},
            },
        },
    )
    _write_json(
        report_dir / "strategy_diagnostics.json",
        {
            "as_of": "2026-04-13",
            "raw_candidate_counts": {"etf_momentum": {"eligible": 1, "selected": 1, "rejected": 1}},
            "records": [
                {
                    "as_of": "2026-04-13",
                    "strategy_id": "etf_momentum",
                    "family": "etf",
                    "symbol": "510500",
                    "eligible": True,
                    "selected": True,
                    "score": 0.8123,
                    "rank": 1,
                    "rank_percentile": 1.0,
                    "universe_size": 2,
                    "peer_distance": None,
                    "raw_features": {},
                    "normalized_features": {},
                    "target_weight": 0.4,
                    "target_weight_before_regime": 0.4,
                    "target_weight_after_regime": 0.28,
                    "rejection_reason": None,
                },
                {
                    "as_of": "2026-04-13",
                    "strategy_id": "etf_momentum",
                    "family": "etf",
                    "symbol": "510300",
                    "eligible": False,
                    "selected": False,
                    "score": -0.1,
                    "rank": None,
                    "rank_percentile": None,
                    "universe_size": 2,
                    "peer_distance": None,
                    "raw_features": {},
                    "normalized_features": {},
                    "target_weight": 0.0,
                    "target_weight_before_regime": 0.0,
                    "target_weight_after_regime": 0.0,
                    "rejection_reason": "score_below_min_momentum",
                },
            ],
        },
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
