# A 股多 Agent 架构演进 Runbook

本文档给后续 agent/工程师使用，说明当前 A 股中低频 paper-only 系统如何按照 `ai-quant-book` 的多智能体章节逐步演进。当前项目不照搬教学代码，而是保留 `src/quant_system/*` 的模块化单体结构，在清晰边界内增加确定性 agent 薄层。

## 参考章节映射

- [Part 4 多智能体概述](https://www.waylandz.com/quant-book/Part4%E6%A6%82%E8%BF%B0/)：多 Agent、Regime、LLM、Risk、Portfolio、Evolution 的总体顺序。
- [第 11 课：为什么需要多智能体](https://www.waylandz.com/quant-book/%E7%AC%AC11%E8%AF%BE%EF%BC%9A%E4%B8%BA%E4%BB%80%E4%B9%88%E9%9C%80%E8%A6%81%E5%A4%9A%E6%99%BA%E8%83%BD%E4%BD%93/)：从单 Agent 到多 Agent 的阶段演进，强调 Risk Agent 一票否决和模块化单体优先。
- [第 12 课：市场状态识别](https://www.waylandz.com/quant-book/%E7%AC%AC12%E8%AF%BE%EF%BC%9A%E5%B8%82%E5%9C%BA%E7%8A%B6%E6%80%81%E8%AF%86%E5%88%AB/) 与第 13 课：Regime 用软权重、不确定状态和危机优先规则，不能用硬切换制造系统性风险。
- [第 14 课：LLM 在量化中的应用](https://www.waylandz.com/quant-book/%E7%AC%AC14%E8%AF%BE%EF%BC%9ALLM%E5%9C%A8%E9%87%8F%E5%8C%96%E4%B8%AD%E7%9A%84%E5%BA%94%E7%94%A8/)：LLM 用于研究、解释和报告，不进入交易控制面。
- [第 15 课：风险控制与资金管理](https://www.waylandz.com/quant-book/%E7%AC%AC15%E8%AF%BE%EF%BC%9A%E9%A3%8E%E9%99%A9%E6%8E%A7%E5%88%B6%E4%B8%8E%E8%B5%84%E9%87%91%E7%AE%A1%E7%90%86/) 与第 16 课：Risk Agent 独立，Portfolio/Position 只建议权重或订单意图，Risk 保留 veto。
- [第 19 课：执行系统](https://www.waylandz.com/quant-book/%E7%AC%AC19%E8%AF%BE%EF%BC%9A%E6%89%A7%E8%A1%8C%E7%B3%BB%E7%BB%9F%20-%20%E4%BB%8E%E4%BF%A1%E5%8F%B7%E5%88%B0%E7%9C%9F%E5%AE%9E%E6%88%90%E4%BA%A4/) 与 [第 21 课：项目实战](https://www.waylandz.com/quant-book/%E7%AC%AC21%E8%AF%BE%EF%BC%9A%E9%A1%B9%E7%9B%AE%E5%AE%9E%E6%88%98/)：执行系统、paper trading、日志、回测质量门和端到端原型。

## 当前状态

当前系统处在 Stage 4-alpha：已有 `RegimeAgent -> SignalAgent -> RiskAgent -> ExecutionAgent -> MonitorAgent` 的日线 paper-only 主链路，并已补入 Stage 5 所需的确定性薄层：`DataAgent`、`PositionAgent`、`MetaAgent`。

核心边界：`SignalAgent` 只输出 `TargetPosition`；`PositionAgent` 只把目标仓位转换为 `OrderIntent`；`RiskAgent` 拥有 veto 权；`ExecutionAgent` 只执行 `RiskDecision.approved_orders`；`MetaAgent` 只做编排和降级；`DataAgent` 只做交易日历、同步、本地历史读取和质检失败传播；LLM Agent 当前只停留在设计文档层。

## Stage 1：单 Agent 基线

目标：验证策略可行性、快速迭代、积累经验。工程落点是使用单策略 `EtfMomentumStrategy` 或 `MainBoardBreakoutStrategy` 跑通本地样本，验证策略能生成目标仓位，paper broker 能在合规条件下产生成交。

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution.MultiAgentEvolutionTest.test_stage1_single_strategy_loop_runs_to_paper_fill
```

禁止：不用 LLM 生成订单；不接实盘券商；不把研究 notebook 当生产入口。

## Stage 2：信号 + 风控分离

目标：把“想交易”和“能不能交易”拆开。`SignalAgent.generate_targets(...) -> list[TargetPosition]`，`RiskAgent.review_orders(...) -> RiskDecision`，`RiskDecision` 是进入执行层的唯一门票。

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution.MultiAgentEvolutionTest.test_stage2_signal_outputs_targets_and_risk_vetoes_invalid_board
```

禁止：Signal 不得输出 `OrderIntent` 或 `Order`；Risk 不得生成策略信号；Risk veto 不得被 Meta/LLM/Execution 覆盖。

## Stage 3：加入执行

目标：将已批准的订单意图送入 paper execution，并保留人工导出路径。`ExecutionAgent.submit_approved_orders(decision, bars)` 只读取 `decision.approved_orders`，`manual_orders.csv` 只导出已批准订单供人工检查。

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution.MultiAgentEvolutionTest.test_stage3_execution_and_manual_export_only_use_approved_orders
```

禁止：`ExecutionAgent` 不得自行重新审核或放宽风控；`manual_orders.csv` 不是自动下单指令；不接真实券商 API。

## Stage 4：加入 Regime

目标：用市场状态调整策略权重，而不是硬切换或让模型接管交易。`RegimeAgent.detect(history) -> RegimeState`，支持 `trending / mean_reverting / crisis / uncertain`，`MonitorAgent` 日报输出 Regime 状态、原因、模式和权重。

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python -m unittest tests.test_regime_agent tests.test_multi_agent_evolution.MultiAgentEvolutionTest.test_stage5_meta_agent_blocks_new_openings_when_regime_uncertain
```

禁止：Regime 不能绕过 Risk；不确定状态不能强行开仓；危机状态不能增加风险敞口。

## Stage 5：完整确定性 Agent 架构

目标：补齐 Data、Meta、Position 的职责边界，形成完整模块化单体。

```text
DataAgent -> RegimeAgent -> SignalAgent -> PositionAgent -> RiskAgent -> ExecutionAgent -> MonitorAgent
MetaAgent 负责单日编排和安全降级
```

接口：`DataAgent.prepare_history(...) -> DataAgentResult`；`PositionAgent.build_order_intents(...) -> list[OrderIntent]`；`MetaAgent.run_day(...) -> AgentLoopResult`；`MetaAgentDecision(mode, reason, can_open_new_positions, regime_override)`。

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python -m unittest tests.test_multi_agent_evolution
```

禁止：MetaAgent 不得直接创建订单；DataAgent 不得伪造交易日历或伪造成功同步；PositionAgent 不得绕过 RiskAgent；Stage 5 仍然不引入微服务、Kafka、K8s 或真实券商。

## 运行时 LLM Agent：最后再做

当前只保留设计草案，不实现运行时。未来接口建议：`ResearchLLMAgent.review_daily_report(report, artifacts) -> LLMAgentAuditRecord`。审计记录至少包含 `prompt_summary`、`input_artifacts`、`output_text`、`recommended_actions`、`accepted_by_human`、`accepted_by_program`、`final_decision_reference`。

允许：解释日报、生成复盘草稿、提出研究假设、标注异常。禁止：生成订单、计算仓位、修改风控参数、禁用止损、触发实盘下单。

## 全量验收

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
PYTHONPATH=src .venv/bin/python scripts/run_backtest_smoke.py
PYTHONPATH=src .venv/bin/python scripts/paper_run_smoke.py
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_smoke.py
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
```

验收通过后，系统仍然只允许 paper trading。连续 5 个交易日 paper 稳定、对账无重大偏差之后，才允许讨论人工下单导出流程；真实 API 实盘不属于本阶段。
