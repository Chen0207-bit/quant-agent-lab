import json
import tempfile
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from strategy_research_run import run_strategy_research


DISABLED_LLM_TOML = """[llm]
enabled = false
provider = "disabled"
model = "disabled"
artifacts_dir = "runs/reports"

[llm.report_agent]
enabled = true

[llm.research_agent]
enabled = false

[llm.sentiment_agent]
enabled = false
"""

ENABLED_RESEARCH_LLM_TOML = """[llm]
enabled = false
provider = "disabled"
model = "disabled"
artifacts_dir = "runs/reports"

[llm.report_agent]
enabled = true

[llm.research_agent]
enabled = true

[llm.sentiment_agent]
enabled = false
"""


class StrategyResearchRunTest(unittest.TestCase):
    def test_research_run_skips_llm_when_feature_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "configs"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "llm.toml").write_text(DISABLED_LLM_TOML, encoding="utf-8")
            result = run_strategy_research(
                start=date(2025, 1, 1),
                end=date(2025, 1, 31),
                symbols=("510300", "510500", "600000"),
                data_dir=root / "data",
                dataset="silver",
                output_dir=root / "research",
                config_dir=config_dir,
                use_simulated=True,
            )

            self.assertIsNone(result.llm_research_path)
            self.assertTrue((result.run_dir / "summary.md").exists())
            self.assertFalse((result.run_dir / "llm_research.json").exists())

    def test_research_run_writes_skipped_llm_artifacts_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "configs"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "llm.toml").write_text(ENABLED_RESEARCH_LLM_TOML, encoding="utf-8")
            result = run_strategy_research(
                start=date(2025, 1, 1),
                end=date(2025, 1, 31),
                symbols=("510300", "510500", "600000"),
                data_dir=root / "data",
                dataset="silver",
                output_dir=root / "research",
                config_dir=config_dir,
                use_simulated=True,
            )

            self.assertIsNotNone(result.llm_research_path)
            payload = json.loads((result.run_dir / "llm_research.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "skipped")
            self.assertTrue((result.run_dir / "llm_research.md").exists())
            self.assertTrue((result.run_dir / "llm_audit.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
