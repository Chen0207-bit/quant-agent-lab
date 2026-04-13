# 交接文档：横截面策略工厂迁移

更新时间：2026-04-14
项目目录：`/home/fc/projects/quant-agent-lab`
当前分支：`arch/llm-foundation`
执行环境：Ubuntu SSH `fc@192.168.93.130`
执行约束：只在 Ubuntu 项目目录写文件；未在 Windows 工作区写项目文件；未提交；未 push。

## 1. 本轮任务

用户要求继续推进“横截面策略工厂迁移”，具体目标是：

1. 先修复半迁移状态导致的红测，恢复 `unittest` 通过。
2. 修正 `ReconcileReport` 字段变更后的静默语义错位。
3. 完成策略工厂 v1 的最小闭环：策略先排名候选，再经组合约束生成目标仓位。
4. 将 `UniverseSnapshot` / `PortfolioConstraints` 接入 `MetaAgent`、`ModularAgentLoop`、`daily_pipeline`。
5. 保持现有硬边界：
   - 不接实盘券商。
   - LLM 不进入下单、仓位、风控 veto 或执行控制面。
   - `RiskAgent` 继续保持确定性一票否决。
   - `ExecutionAgent` 只执行已批准订单。

## 2. 本轮实际完成内容

### 2.1 领域模型和配置

已在 `src/quant_system/common/models.py` 增加或扩展：

- `UniverseMember`
- `UniverseSnapshot`
- `PortfolioConstraints`
- `StrategyContext`
- `ScoredCandidate`
- `StrategyDiagnosticRecord` 新增 `family`、`rank`、`rank_percentile`、`universe_size`、`peer_distance`、`normalized_features`、`target_weight_before_regime`、`target_weight_after_regime`
- `ReconcileReport` 改为表达：`cash`、`equity`、`unrealized_pnl`、`is_consistent`、`reasons`

已在 `src/quant_system/config/settings.py` 增加：

- `UniverseSymbolMetadata`
- `UniverseConfig.symbol_metadata`
- `load_universe_config()` 对 `[universe.metadata.<symbol>]` 的解析

旧配置仍然可用；没有强制要求 `configs/universe.toml` 必须新增 metadata。

### 2.2 Universe snapshot

已在 `src/quant_system/data/universe.py` 增加：

- `build_universe_snapshot(as_of, instruments, bars, config)`
- ETF 未配置行业时默认 industry 为 `ETF`
- 股票未配置行业时默认 `unknown`
- `liquidity_cny` 优先使用 `bar.amount`，缺失时使用 `bar.volume * bar.close`

`daily_pipeline` 现在会输出 `universe_snapshot.json` 到日报目录。

### 2.3 策略协议和 baseline 策略

已在 `src/quant_system/strategies/base.py` 增加 `CrossSectionalStrategy` 协议：

- `rank_candidates(context, history, portfolio)`
- `diagnose(as_of, history, portfolio, context=None)`
- `is_rebalance_day(as_of, history)`

已在 `src/quant_system/strategies/baseline.py` 完成：

- `EtfMomentumStrategy.family = "etf"`
- `MainBoardBreakoutStrategy.family = "main_board"`
- 两个策略都实现 `rank_candidates()`
- 两个策略都实现 `is_rebalance_day()`，当前支持 `daily`、`weekly`、`monthly`，未知值回退为每日可调仓
- `diagnose()` 现在输出 rank、rank percentile、universe size、target weight before/after regime 等审计字段
- `generate_targets()` 保持旧调用兼容

说明：当前 `target_weight_after_regime` 在单独调用 strategy `diagnose()` 时仍等于策略自身权重；在 `SignalAgent.generate_signal_plan()` 中会按 regime weight 计算。

### 2.4 SignalAgent 和组合构建

已在 `src/quant_system/agents/signal_agent.py` 增加：

- `SignalPlan`
- `generate_signal_plan(...)`
- 排名候选 -> regime weight -> 组合约束 -> target 输出的主链路
- 对 `strategy_id` 和 `family` 两种 regime weight key 的兼容
- 对 turnover budget 保留旧持仓导致目标符号不在新信号里的情况，增加 fallback reason：`portfolio_constraint_retains_existing_position`

`generate_targets()` 保持兼容包装；当外部没有显式传入 `portfolio_constraints` 时，使用宽松约束，避免旧单元测试和旧调用被默认 `max_position_weight=0.20` 改变语义。

新增文件：`src/quant_system/portfolio/construction.py`

当前实现的组合约束：

- single-name cap
- industry cap
- gross exposure cap，按 `1 - min_cash_buffer_pct`
- turnover budget

## 3. 主链路接入

### 3.1 MetaAgent

`src/quant_system/agents/meta_agent.py` 现在接受：

- `universe_snapshot: UniverseSnapshot | None`
- `portfolio_constraints: PortfolioConstraints | None`

`MetaAgent.run_day()` 现在调用 `SignalAgent.generate_signal_plan()`，但仍保留既有安全边界：

- `MetaAgent` 不直接创建订单。
- `MetaAgent` 不批准风险。
- `MetaAgent` 不绕过 `RiskAgent`。
- crisis / uncertain regime 下仍通过 meta boundary 限制新开仓。

### 3.2 ModularAgentLoop

`src/quant_system/app/main_loop.py` 现在：

- 接受可选 `universe_config`
- 接受可选 `portfolio_constraints`
- 若未显式传入组合约束，则从 `RiskConfig` 映射：
  - `max_position_weight`
  - `max_daily_turnover_pct` -> `turnover_budget`
  - `min_cash_buffer_pct`
- 每个交易日用当日 bars 构建 `UniverseSnapshot` 并传给 `MetaAgent`

### 3.3 Daily pipeline

`src/quant_system/app/daily_pipeline.py` 现在：

- 将 `universe_config` 传入 `ModularAgentLoop`
- 在日报目录写入 `universe_snapshot.json`
- 仍维持原有 `daily_summary.md/json`、`manual_orders.csv`、`data_sync_report.json`、`strategy_diagnostics.json`、LLM skipped artifacts 输出

## 4. ReconcileReport 修复

已在 `src/quant_system/execution/paper.py` 修复 `PaperBroker.reconcile()`：

- 不再按旧字段位置传 `positions_count` / `open_orders_count`
- 改为 keyword 构造 `ReconcileReport`
- `equity = cash + positions market value`
- `unrealized_pnl = sum(position.market_value - qty * avg_cost)`
- `reasons` 记录负现金、负持仓、可用数量异常、残留 open orders 等问题

已同步修复测试中的手写 `ReconcileReport(...)`，改为 keyword args，避免未来再次出现位置参数静默错位。

## 5. 测试和验证结果

本轮最后一次验证全部通过。

### 5.1 编译

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
```

结果：通过。

### 5.2 单元测试

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

结果：通过，`51 tests OK`。

新增或增强的测试覆盖：

- `tests/test_config_universe.py`：universe metadata -> snapshot、liquidity 字段
- `tests/test_daily_pipeline.py`：`universe_snapshot.json` 输出、ETF 默认 industry 为 `ETF`
- `tests/test_paper_broker.py`：`ReconcileReport.equity`、`ReconcileReport.unrealized_pnl`、`ReconcileReport.reasons`
- `tests/test_signal_agent.py`：cross-sectional candidates ranking、portfolio constraints cap、turnover budget 保留旧持仓时的 reason fallback
- `tests/test_multi_agent_evolution.py`：`ReconcileReport` 手写构造改为 keyword args

### 5.3 Smoke 验证

以下脚本均通过：

```bash
PYTHONPATH=src .venv/bin/python scripts/run_backtest_smoke.py
PYTHONPATH=src .venv/bin/python scripts/paper_run_smoke.py
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_smoke.py
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
PYTHONPATH=src .venv/bin/python scripts/strategy_research_run.py --use-simulated --symbols 510300,510500,600000 --end 2025-01-31
```

关键输出：

- backtest smoke：通过，Return 约 `2.63%`，Orders `6`，Fills `6`，Rejections `0`
- paper smoke：通过，`risk_action = APPROVE`，`orders = ["FILLED"]`，`consistent = true`
- agent loop smoke：通过，最后日期 `2025-01-30`，`Risk action = APPROVE`
- daily pipeline：通过，因 A 股真实交易日历，`--as-of 2025-01-31` 实际落到 `2025-01-27`
- strategy research：通过，`best_candidate_id = etf:9979bf0f2e`，`llm_research_path = null`

### 5.4 Diff 检查

```bash
git diff --check
```

结果：通过，无 whitespace/error 输出。

## 6. 当前 Git 状态

当前仍未提交、未 push。

`git status --short --branch` 显示：

```text
## arch/llm-foundation
 M src/quant_system/agents/meta_agent.py
 M src/quant_system/agents/signal_agent.py
 M src/quant_system/app/daily_pipeline.py
 M src/quant_system/app/main_loop.py
 M src/quant_system/common/models.py
 M src/quant_system/config/settings.py
 M src/quant_system/data/universe.py
 M src/quant_system/execution/paper.py
 M src/quant_system/features/factors.py
 M src/quant_system/strategies/base.py
 M src/quant_system/strategies/baseline.py
 M tests/test_config_universe.py
 M tests/test_daily_pipeline.py
 M tests/test_multi_agent_evolution.py
 M tests/test_paper_broker.py
 M tests/test_signal_agent.py
?? docs/codex_handoff_2026-04-13.md
?? docs/completion_reports/
?? docs/handoff_2026-04-14_zh.md
?? docs/交接文档.md
?? src/quant_system/portfolio/construction.py
```

`git diff --stat` 当前约为：

```text
16 files changed, 875 insertions(+), 37 deletions(-)
```

另有未跟踪文件：

- `docs/codex_handoff_2026-04-13.md`：之前留下的英文交接文档，内容已过期，仍未修改
- `docs/completion_reports/`：当前已存在的未跟踪目录，本轮未展开检查其内容
- `docs/handoff_2026-04-14_zh.md`：本文件，本轮新增中文交接文档
- `docs/交接文档.md`：之前已有的中文交接文档，内容已过期，仍未修改
- `src/quant_system/portfolio/construction.py`：本轮策略工厂迁移新增的组合构建模块

## 7. 当前需要注意的风险

1. 工作树仍是脏的，但这次脏改动已经从“半迁移红测”恢复到“可编译、可测试、smoke 通过”。
2. 尚未提交，所以如果要继续开发，建议先 review diff，再按一次清晰提交落地。
3. 尚未 push，远端 Git 同步问题仍未处理。
4. `docs/codex_handoff_2026-04-13.md` 和 `docs/交接文档.md` 都是旧信息，下一步最好选择一个作为 canonical handoff 文档，或删除/归档过期文档，避免误导后续接手者。
5. 组合构建目前是 v1 规则，不是完整 Barra/AQR 风险模型；它只覆盖 single-name、industry、gross exposure、turnover、cash buffer。
6. `rebalance_frequency` 当前只在策略类字段里支持，尚未从 `configs/strategy.toml` 显式配置接入。

## 8. 建议下一步

推荐顺序：

1. 先 review 当前 diff，确认这批策略工厂迁移可以作为一个提交。
2. 如果接受，提交建议：

```bash
git add src tests docs/handoff_2026-04-14_zh.md
git commit -m "feat: add cross-sectional strategy factory foundation"
```

3. 再处理远端同步：
   - 优先修 Ubuntu 到 GitHub 的 SSH key
   - 然后同步 `main` 和 `arch/llm-foundation`
4. 再继续下一阶段：
   - 将 `rebalance_frequency` 接入 `configs/strategy.toml`
   - 扩展 ETF / 主板 universe
   - 给 `strategy_research_run.py` 增加 family research 输出、failure analysis、IC/RankIC、行业暴露
   - 之后再考虑 LLM Phase 3 文本/新闻特征链路

## 9. 一句话结论

本轮已经把横截面策略工厂从“半迁移、测试失败”推进到“v1 主链路可跑、51 个单测通过、主要 smoke 通过”的状态；尚未提交和远端同步，下一位接手者应先 review diff 并提交，再处理 GitHub 同步。
