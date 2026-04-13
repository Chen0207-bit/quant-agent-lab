# Quant Agent Lab 中文 README

Quant Agent Lab 是一个面向 A 股日频、低频、paper-only 研究与交易流水线的量化工程实验室。当前目标不是实盘自动交易，而是把数据、策略研究、回测、paper trading、风控审计、日报和只读 LLM 研究辅助做成可验证、可回滚的工程闭环。

## 当前阶段

当前实现阶段：确定性 A 股 paper-trading MVP + 横截面策略工厂 v1 + 只读 LLM 辅助层 Phase 2。

已经落地：

- A 股日频数据读取、缓存、质量检查、回测和 paper trading。
- ETF 动量与主板突破两个 baseline 策略族。
- 横截面策略工厂 v1：`rank_candidates()` -> regime weight -> portfolio constraints -> target generation。
- `UniverseSnapshot`、`PortfolioConstraints`、`StrategyContext`、`ScoredCandidate` 等策略上下文类型。
- `SignalAgent.generate_signal_plan(...)` 新信号链路，同时保留旧 `generate_targets()` 兼容入口。
- 只读 LLM 日报审阅和离线策略研究审阅。
- 本地 git history + verified bundle + GitHub 分支/tag 的版本备份流程。

尚未落地：

- 实盘券商接入或真实下单。
- LLM 参与信号、仓位、风控 veto、订单执行或策略配置改写。
- walk-forward、Barra attribution、新闻/情绪特征闭环和生产级组合归因。

## 安全边界

交易控制面保持确定性：

- `RiskAgent` 继续保持硬 veto。
- `ExecutionAgent` 只执行 approved orders。
- LLM 不生成 `TargetPosition`。
- LLM 不生成 `OrderIntent`。
- LLM 不生成或覆盖 `RiskDecision`。
- LLM 不修改策略配置。
- LLM 不触发 broker execution。

## 核心链路

```text
DataAgent
  -> RegimeAgent
  -> SignalAgent
  -> PositionAgent
  -> RiskAgent
  -> ExecutionAgent
  -> MonitorAgent
  -> MetaAgent orchestration
```

数据与交易流水线：

```text
AKShare / 本地 bars
  -> raw / silver / gold datasets
  -> UniverseSnapshot
  -> 策略候选排名
  -> 组合约束
  -> 目标仓位
  -> 确定性风控
  -> PaperBroker / manual orders
  -> 日报、诊断、审计产物
```

## 快速运行

项目固定在 Ubuntu 环境运行：

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

常用 smoke：

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python scripts/run_backtest_smoke.py
PYTHONPATH=src .venv/bin/python scripts/paper_run_smoke.py
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_smoke.py
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
PYTHONPATH=src .venv/bin/python scripts/strategy_research_run.py --use-simulated --symbols 510300,510500,600000 --end 2025-01-31
```

## 主要产物

日报产物：

```text
runs/reports/<trade_date>/
  daily_summary.md
  daily_summary.json
  data_sync_report.json
  strategy_diagnostics.json
  universe_snapshot.json
  manual_orders.csv
  llm_report.md
  llm_report.json
  llm_audit.jsonl
```

离线策略研究产物：

```text
runs/strategy_research/<run_id>/
  config.json
  candidates.json
  metrics.json
  ranking.json
  strategy_diagnostics.json
  summary.md
  llm_research.md
  llm_research.json
  llm_audit.jsonl
```

## 版本与备份

当前长期规则：Ubuntu 本地 git history 是 canonical source of truth。GitHub 远端分支/tag 用于协作和备份；每个完成阶段都应生成 verified bundle。

本地 bundle：

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python scripts/git_snapshot_sync.py --skip-remote --branches main,arch/llm-foundation,v2026.04.14-llm-research
```

远端发布：

```bash
cd /home/fc/projects/quant-agent-lab
git push -u origin arch/llm-foundation
git push origin v2026.04.14-llm-research
```

## 文档入口

- 完整架构与策略阶段说明：`docs/system_manual_2026-04-14_zh.md`
- Git 工作流：`docs/git_workflow.md`
- LLM 架构计划：`docs/llm_architecture_plan.md`
- Ubuntu 运行手册：`docs/ubuntu_runbook.md`
- 当前交接文档：`docs/handoff_2026-04-14_zh.md`

## 当前版本

- 分支：`arch/llm-foundation`
- 阶段标签：`v2026.04.14-llm-research`
- 阶段状态：横截面策略工厂 v1 与 LLM Research Phase 2 已完成并通过本地验证。
