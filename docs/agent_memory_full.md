# Quant Agent Lab 完整项目记忆

本文档用于把当前对 `/home/fc/projects/quant-agent-lab` 的项目记忆交给另一个 agent 或后续会话继续执行。内容只包含项目背景、工程状态、设计决策和操作信息，不包含隐藏系统提示或内部推理。

## 1. 固定环境

- 只在 Ubuntu 写项目文件，不在 Windows 工作区写此项目。
- Ubuntu SSH：`ssh fc@192.168.93.130`
- 项目目录：`/home/fc/projects/quant-agent-lab`
- 当前环境：Ubuntu，Node `v22.22.2`，npm `10.9.7`，OpenClaw `2026.4.11`，Codex CLI `0.120.0`
- OpenClaw gateway：running，RPC probe ok，监听 `*:18789`
- Python 虚拟环境：`/home/fc/projects/quant-agent-lab/.venv`
- 当前不是 git 仓库，`git status` 会返回“不是 git 仓库”。

## 2. 业务目标

目标是搭建一个 A 股中低频量化交易系统，不是教程复现，也不是 notebook-only。系统必须可运行、可验证、可迭代、可长期维护。

已确认约束：

- 市场：A 股。
- 频率：日线/中低频。
- 资金规模：约 10 万人民币。
- 数据源：优先免费数据，MVP 使用 AKShare。
- 交易阶段：MVP 只做 paper trading，不接真实券商 API。
- 标的边界：ETF 优先，主板样本股用于工程验证；暂不做创业板、科创板、北交所。
- 运行方式：Ubuntu 单机模块化单体，不上微服务、Kafka、K8s。
- Agent 边界：Agent 可以研究、解释、编排和报告；不能绕过确定性风控，不能直接实盘下单。

## 3. 参考蓝本

系统设计参考 `ai-quant-book`，但不照搬教学代码。书中的第 21 课 `agents/core/strategies/main.py` 是概念参考；本项目保留 `src/quant_system/*` 的工程分层。

参考链接：

- ai-quant-book 中文稿件：https://github.com/waylandzhang/ai-quant-book/tree/main/manuscript/cn
- Part 4 多智能体概述：https://www.waylandz.com/quant-book/Part4%E6%A6%82%E8%BF%B0/
- 第 11 课：为什么需要多智能体：https://www.waylandz.com/quant-book/%E7%AC%AC11%E8%AF%BE%EF%BC%9A%E4%B8%BA%E4%BB%80%E4%B9%88%E9%9C%80%E8%A6%81%E5%A4%9A%E6%99%BA%E8%83%BD%E4%BD%93/
- 第 12 课：市场状态识别：https://www.waylandz.com/quant-book/%E7%AC%AC12%E8%AF%BE%EF%BC%9A%E5%B8%82%E5%9C%BA%E7%8A%B6%E6%80%81%E8%AF%86%E5%88%AB/
- 第 14 课：LLM 在量化中的应用：https://www.waylandz.com/quant-book/%E7%AC%AC14%E8%AF%BE%EF%BC%9ALLM%E5%9C%A8%E9%87%8F%E5%8C%96%E4%B8%AD%E7%9A%84%E5%BA%94%E7%94%A8/
- 第 15 课：风险控制与资金管理：https://www.waylandz.com/quant-book/%E7%AC%AC15%E8%AF%BE%EF%BC%9A%E9%A3%8E%E9%99%A9%E6%8E%A7%E5%88%B6%E4%B8%8E%E8%B5%84%E9%87%91%E7%AE%A1%E7%90%86/
- 第 19 课：执行系统：https://www.waylandz.com/quant-book/%E7%AC%AC19%E8%AF%BE%EF%BC%9A%E6%89%A7%E8%A1%8C%E7%B3%BB%E7%BB%9F%20-%20%E4%BB%8E%E4%BF%A1%E5%8F%B7%E5%88%B0%E7%9C%9F%E5%AE%9E%E6%88%90%E4%BA%A4/
- 第 21 课：项目实战：https://www.waylandz.com/quant-book/%E7%AC%AC21%E8%AF%BE%EF%BC%9A%E9%A1%B9%E7%9B%AE%E5%AE%9E%E6%88%98/

## 4. 核心架构

当前系统是模块化单体，完整确定性 Agent 链路如下：

```text
DataAgent
  -> RegimeAgent
  -> SignalAgent
  -> PositionAgent
  -> RiskAgent
  -> ExecutionAgent
  -> MonitorAgent
MetaAgent 负责单日编排与安全降级
```

关键边界：

- `DataAgent`：交易日历、数据同步、本地历史读取、质检失败停止。
- `RegimeAgent`：输出市场状态和策略权重。
- `SignalAgent`：输出 `TargetPosition`，不输出订单。
- `PositionAgent`：把目标仓位转成 A 股 `OrderIntent`，不批准交易。
- `RiskAgent`：确定性 `RiskEngine` 封装，拥有不可覆盖的 veto 权。
- `ExecutionAgent`：只执行 `RiskDecision.approved_orders`，当前只连 `PaperBroker`。
- `MonitorAgent`：生成 Markdown 日报、JSON 摘要、manual orders CSV 和数据同步报告。
- `MetaAgent`：编排和降级，不直接创建订单，不覆盖风控。
- 运行时 LLM Agent：当前不实现，只允许未来作为研究、解释、复盘和异常标注层。

## 5. 已实现文件概览

主要实现：

- `src/quant_system/data/akshare_adapter.py`：AKShare 日线适配，中文字段映射已修复。
- `src/quant_system/data/storage.py`：Parquet + DuckDB 本地存储。
- `src/quant_system/data/manager.py`：`DataManager`、`DataSyncReport`、带重试的数据同步。
- `src/quant_system/data/calendar.py`：AKShare 交易日历和缓存，不能用普通工作日伪装 A 股交易日。
- `src/quant_system/data/universe.py`：MVP universe 构建。
- `src/quant_system/config/settings.py`：用标准库 `tomllib` 读取配置。
- `src/quant_system/agents/data_agent.py`：确定性数据准备 Agent。
- `src/quant_system/agents/regime_agent.py`：确定性 Regime 识别。
- `src/quant_system/agents/signal_agent.py`：策略目标仓位聚合。
- `src/quant_system/agents/position_agent.py`：目标仓位转订单意图。
- `src/quant_system/agents/risk_agent.py`：确定性风控封装。
- `src/quant_system/agents/execution_agent.py`：paper-only 执行封装。
- `src/quant_system/agents/meta_agent.py`：单日编排、安全降级、Risk 异常 fail-closed。
- `src/quant_system/agents/monitor_agent.py`：日报和 JSON 输出，包含 `regime_health`。
- `src/quant_system/app/main_loop.py`：单进程 `ModularAgentLoop`。
- `src/quant_system/app/daily_pipeline.py`：日终 pipeline。
- `scripts/daily_pipeline.py`：日终入口脚本。

主要文档：

- `docs/architecture.md`：整体架构。
- `docs/mvp_acceptance.md`：MVP 验收和 Agent 边界验收。
- `docs/ubuntu_runbook.md`：Ubuntu 运行说明。
- `docs/agent_handoff_current_status.md`：之前给另一个 agent 的交接摘要。
- `docs/multi_agent_evolution_runbook.md`：按 Stage 1-5 的多 Agent 演进说明。
- `docs/操作说明书.md`：面向操作者的启动、验收和禁止事项。
- `docs/agent_memory_full.md`：本文档。

## 6. Universe 与配置

`configs/universe.toml` 中的样本池：

- ETF：`510300`、`510500`、`159915`
- 主板工程样本：`600000`、`600519`、`601318`、`601888`、`000001`、`000333`、`000651`、`002415`

这些样本只用于工程链路验证，不构成投资建议。

当前 MVP 默认排除：

- 创业板：`300/301` 前缀。
- 科创板：`688/689` 前缀。
- 北交所：`8/4` 前缀。
- ST、停牌、未知板块。

## 7. 多 Agent 阶段演进状态

当前视为 Stage 4-alpha，并已补入 Stage 5 的确定性薄层。

Stage 1：单 Agent 基线

- 目标：验证策略可行性、快速迭代、积累经验。
- 现状：已有单策略链路和验收测试。
- 禁止：LLM 生成订单、实盘、notebook 作为生产入口。

Stage 2：Signal + Risk 分离

- `SignalAgent` 输出 `TargetPosition`。
- `RiskAgent` 输出 `RiskDecision`。
- `RiskDecision` 是进入执行层的唯一门票。

Stage 3：加入 Execution

- `ExecutionAgent` 只执行 approved orders。
- `manual_orders.csv` 只导出已批准订单，供人工检查，不是自动交易指令。

Stage 4：加入 Regime

- `RegimeAgent` 输出 `trending / mean_reverting / crisis / uncertain`。
- `SignalAgent` 按 Regime 权重缩放目标仓位。
- `MetaAgent` 在 `uncertain` 下禁止新开仓，在 `crisis` 下只允许退出。
- `MonitorAgent` 输出 Regime mode 和 Regime weights。

Stage 5：完整确定性 Agent 架构

- 已新增 `DataAgent`、`PositionAgent`、`MetaAgent`。
- `MetaAgent` 遇到 Risk 异常时返回 `LIQUIDATE_ONLY`，不批准新订单。
- 仍然不引入微服务、Kafka、K8s 或真实券商。

运行时 LLM Agent：最后再做

- 当前只写设计边界，不接模型、不接 API key。
- 未来只允许做日报解释、复盘草稿、异常标注、研究假设。
- 禁止生成订单、计算仓位、修改风控参数、禁用止损、触发实盘下单。

## 8. 启动系统

当前系统不是常驻服务，而是日终批处理 pipeline。

进入 Ubuntu：

```bash
ssh fc@192.168.93.130
cd /home/fc/projects/quant-agent-lab
```

运行日终 pipeline：

```bash
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
```

如果 `--as-of` 是非交易日，系统会用真实 A 股交易日历回退到最近交易日。例如 `2025-01-31` 是春节休市日，当前验收中回退到了 `2025-01-27`。

省略 `--as-of` 时，系统默认取今天之前最近一个 A 股交易日：

```bash
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --symbols 510300,510500 --lookback-days 5
```

## 9. 输出位置

日终报告输出：

```text
runs/reports/YYYY-MM-DD/
  daily_summary.md
  daily_summary.json
  manual_orders.csv
  data_sync_report.json
```

检查示例：

```bash
cat runs/reports/2025-01-27/daily_summary.md
cat runs/reports/2025-01-27/daily_summary.json
cat runs/reports/2025-01-27/manual_orders.csv
cat runs/reports/2025-01-27/data_sync_report.json
```

最近一次已验证的 `2025-01-27` 报告中：

- `quality_passed: true`
- `bars_written: 128`
- `symbols: 510300, 510500`
- Regime 为 `uncertain`
- Meta decision 为 `defensive_hold`
- `can_open_new_positions: false`
- manual orders 为空，仅有 CSV 表头

## 10. 常用验收命令

编译和全量单测：

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Smoke：

```bash
PYTHONPATH=src .venv/bin/python scripts/run_backtest_smoke.py
PYTHONPATH=src .venv/bin/python scripts/paper_run_smoke.py
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_smoke.py
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
```

分阶段验收：

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution.MultiAgentEvolutionTest.test_stage1_single_strategy_loop_runs_to_paper_fill
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution.MultiAgentEvolutionTest.test_stage2_signal_outputs_targets_and_risk_vetoes_invalid_board
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution.MultiAgentEvolutionTest.test_stage3_execution_and_manual_export_only_use_approved_orders
PYTHONPATH=src .venv/bin/python -m unittest tests.test_regime_agent
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution
```

## 11. 最近验证结果

最近一次回归已通过：

- `.venv/bin/python -m compileall -q src tests scripts main.py`：通过。
- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`：通过，35 tests OK。
- `scripts/run_backtest_smoke.py`：通过，Start `2025-01-01`，End `2025-01-30`，Return `4.80%`，Orders `8`，Fills `8`，Rejections `0`。
- `scripts/paper_run_smoke.py`：通过，`risk_action=APPROVE`，orders `FILLED`，fills `1`，reconcile consistent。
- `scripts/run_agent_loop_smoke.py`：通过，日报包含 Regime mode/weights。
- `scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5`：通过，输出 `runs/reports/2025-01-27`。

## 12. 关键禁止事项

- 不在 Windows 工作区写本项目文件。
- 不接真实券商 API。
- 不用 LLM 生成订单、计算仓位、修改风控参数或触发下单。
- 不让 `MetaAgent`、`SignalAgent`、`PositionAgent` 覆盖 `RiskAgent` veto。
- 不把 `manual_orders.csv` 当成自动交易指令。
- 不用普通工作日伪装 A 股交易日历。
- AKShare 网络或字段异常时必须失败并报告，不生成伪成功结果。
- 不引入 Qlib/vectorbt/Backtrader/NautilusTrader/VeighNa/Kafka/K8s 作为当前 MVP 依赖。

## 13. 下一步建议

优先顺序：

1. 运行至少 5 个交易日的 paper pipeline，观察数据同步、Regime、Risk、对账和报告稳定性。
2. 补充更真实的 ETF universe 和主板样本池配置，但保持工程验证与投资建议分离。
3. 增加日报对比：上一交易日 vs 当前交易日的信号、目标权重、Meta 决策变化。
4. 增加成本/滑点报告反哺，但仍然只做 paper。
5. 在 Stage 1-5 稳定后，再设计运行时 LLM Agent 的审计记录，不接实盘控制面。

## 14. 给下一个 agent 的执行原则

- 先读 `docs/操作说明书.md`、`docs/multi_agent_evolution_runbook.md` 和本文档。
- 先跑 `compileall` 和全量单测，再做修改。
- 修改前确认当前工作目录是 `/home/fc/projects/quant-agent-lab`。
- 如果涉及中文文档，优先用 UTF-8/base64 或可靠编辑方式，避免 SSH 管道把中文写成问号。
- 新增任何 Agent 时，先写清输入/输出和权限边界，再写代码。
- 任何能影响订单、仓位、风控、执行的变更，都必须有测试证明不能绕过 `RiskAgent`。
