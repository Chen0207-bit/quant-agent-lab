# Quant Agent Lab 当前架构与策略阶段说明书

更新日期：2026-04-14
项目目录：`/home/fc/projects/quant-agent-lab`
主工作分支：`arch/llm-foundation`

## 1. 当前结论

Quant Agent Lab 目前处在“确定性 A 股 paper-trading MVP + 横截面策略工厂 v1 + 只读 LLM 辅助层 Phase 2”的阶段。

当前已经落地的是：

- 日频 A 股 paper-trading 控制面，交易链路仍由确定性代码驱动。
- ETF 动量与主板突破两个 baseline 策略族，已迁移到横截面 rank -> regime weight -> portfolio constraints -> target generation 的 v1 形态。
- `UniverseSnapshot`、`PortfolioConstraints`、`StrategyContext`、`ScoredCandidate` 等策略工厂基础类型已进入主链路。
- `SignalAgent.generate_signal_plan(...)` 已成为新信号链路入口，旧 `generate_targets()` / `diagnose_strategies()` 保持兼容。
- LLM Phase 1 日报审阅已存在；LLM Phase 2 离线策略研究审阅已接入 `scripts/strategy_research_run.py`。
- Git 备份路线进入双轨：Ubuntu 本地 git history 是真实源；远端 GitHub 可在 SSH 不可用时用 API 快照兜底；每个阶段版本都应生成 verified bundle。

当前没有落地的是：

- 真实券商或实盘下单。
- LLM 参与信号、仓位、风控、执行或配置改写。
- walk-forward、Barra attribution、新闻/情绪因子闭环、组合归因平台。
- 远端 GitHub 原生 SSH push 的环境修复；如果没有 SSH 或 token，远端发布会被阻塞，但本地版本和 bundle 仍可完成。

## 2. 架构实现阶段

### 2.1 控制面

当前控制面是确定性模块化单体，不是 autonomous trading bot。

核心链路：

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

职责边界：

- `DataAgent`：读取或同步行情数据，组织日频 bars。
- `RegimeAgent`：生成市场状态与风险权重。
- `SignalAgent`：调用策略族排名、生成 signal plan，并把结果转换成目标仓位。
- `PositionAgent`：读取 paper broker 状态与当前组合。
- `RiskAgent`：执行确定性 veto，仍有硬否决权。
- `ExecutionAgent`：只执行 approved orders。
- `MonitorAgent`：写日报、诊断和审计产物。
- `MetaAgent` / `ModularAgentLoop`：编排上述 deterministic agents，并传入可选的 universe snapshot 和 portfolio constraints。

### 2.2 数据与快照

当前 daily pipeline 会从 bars、instruments、universe metadata 组装 `UniverseSnapshot`。旧 universe 配置仍可用，新配置可以逐步补 `[universe.metadata.<symbol>]`。

快照用途：

- 给策略候选打分提供 board、family、industry、risk flags 等上下文。
- 给组合构造层提供 universe size、ranking、行业 cap、单名 cap、turnover budget 等约束输入。
- 给诊断与审计产物补齐 family、rank、universe_size、target_weight_before_regime、target_weight_after_regime 等字段。

### 2.3 LLM 层

LLM 层目前是只读辅助层。

已实现阶段：

- Phase 1：日报审阅，入口在 daily report artifacts 写出之后。
- Phase 2：离线策略研究审阅，入口在 `scripts/strategy_research_run.py` 写出 deterministic artifacts 之后。
- Phase 3：新闻/情绪 agent 仍是 scaffold，不进入交易路径。

研究 LLM 产物合同：

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

`llm_research.json` 固定字段：

```text
agent_name
status
provider
model
prompt_hash
input_artifacts
best_candidate_id
research_summary
recommended_experiments
promotion_assessment
metadata
```

安全边界：

- LLM 不生成 `TargetPosition`。
- LLM 不生成 `OrderIntent`。
- LLM 不生成或覆盖 `RiskDecision`。
- LLM 不改策略配置。
- LLM 不触发 broker execution。
- LLM 失败只写 `error` artifact 和 audit，不会删除或改写 deterministic research artifacts。

## 3. 策略进化阶段

策略当前处于“横截面策略工厂 v1”阶段。

已完成能力：

- `etf_momentum` 策略族 family 固定为 `etf`。
- `main_board_breakout` 策略族 family 固定为 `main_board`。
- 两个策略族都提供 `rank_candidates()` 与 `is_rebalance_day()`。
- `diagnose()` 从候选排名结果生成策略诊断。
- `generate_targets()` 保留旧调用兼容，但新链路优先走 `SignalAgent.generate_signal_plan(...)`。
- 组合层会处理单名 cap、行业 cap、总仓位、turnover budget 等约束。
- `PaperBroker.reconcile()` 已按新 `ReconcileReport` 字段输出 `cash`、`equity`、`unrealized_pnl`、`is_consistent`、`reasons`。

还未进入的阶段：

- ETF 与主板更大 universe 的生产级 metadata 扩展。
- rebalance frequency 从配置层完整参数化。
- defensive quality sleeve。
- walk-forward / OOS 研究协议。
- IC / RankIC / failure analysis 报告。
- Barra 或行业风格归因。
- 新闻、公告、情绪特征进入研究特征链路。

策略演进路线建议：

1. 先把当前横截面 v1 作为稳定版本固定下来。
2. 再新增 universe metadata 与 rebalance frequency 配置化。
3. 然后做 walk-forward 研究框架，避免继续只用单段 backtest 决策。
4. 最后再考虑 news/sentiment 特征与 attribution，而不是提前把 LLM 放进交易控制面。

## 4. 本地版本、远端版本与回滚

### 4.1 当前规则

- Ubuntu 本地 git history 是 canonical source of truth。
- 远端 GitHub API 快照只是 SSH 修复前的备份状态，不是 history-perfect mirror。
- 每个完成的本地阶段版本都必须有 verified bundle。
- 如果 SSH 可用，优先使用原生 `git push`。
- 如果 SSH 不可用但 `GITHUB_TOKEN` 或 `GH_TOKEN` 可用，使用 API 快照同步远端分支和版本标签。
- 如果 SSH 和 token 都不可用，只完成本地 commit + bundle，并明确记录远端阻塞。

### 4.2 本地验证命令

```bash
cd /home/fc/projects/quant-agent-lab
.venv/bin/python -m compileall -q src tests scripts main.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
git diff --check
```

### 4.3 smoke 命令

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python scripts/run_backtest_smoke.py
PYTHONPATH=src .venv/bin/python scripts/paper_run_smoke.py
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_smoke.py
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py --as-of 2025-01-31 --symbols 510300,510500 --lookback-days 5
PYTHONPATH=src .venv/bin/python scripts/strategy_research_run.py --use-simulated --symbols 510300,510500,600000 --end 2025-01-31
```

### 4.4 bundle 备份

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python scripts/git_snapshot_sync.py --skip-remote
```

bundle 默认写到：

```text
/home/fc/git-backups/quant-agent-lab-<timestamp>.bundle
```

### 4.5 原生 SSH 发布

```bash
cd /home/fc/projects/quant-agent-lab
git push -u origin arch/llm-foundation
git push origin v2026.04.14-llm-research
```

如果远端同名 tag 已存在，使用递增后缀，例如：

```text
v2026.04.14-llm-research.1
```

### 4.6 API 快照发布

需要 Ubuntu 环境里存在有写权限的 `GITHUB_TOKEN` 或 `GH_TOKEN`。

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python scripts/git_snapshot_sync.py   --branches main,arch/llm-foundation   --tag-name v2026.04.14-llm-research   --tag-branch arch/llm-foundation
```

该流程会：

- 要求 worktree 干净。
- 生成 verified bundle。
- 同步远端 `main` 与 `arch/llm-foundation` 快照。
- 在远端 `arch/llm-foundation` 快照提交上创建 annotated tag；若同名 tag 已存在，自动使用 `.1`、`.2` 等后缀。

### 4.7 回滚

优先用 revert，不用 `git reset --hard` 改共享历史。

```bash
git log --oneline --decorate -n 20
git revert <commit_sha>
```

从 bundle 恢复：

```bash
git clone /home/fc/git-backups/quant-agent-lab-<timestamp>.bundle restored-quant-agent-lab
```

## 5. 当前阶段验收清单

完成本阶段时必须满足：

- `compileall` 通过。
- 全量 `unittest discover -s tests` 通过。
- smoke 命令通过。
- `git diff --check` 通过。
- 本地 commit 已创建。
- 本地 tag 已创建。
- verified bundle 已创建并通过 `git bundle verify`。
- 远端分支与 tag 已 push；如果失败，最终报告必须写清楚 SSH/token 阻塞原因。

## 6. 下一阶段建议

优先顺序：

1. 修复 Ubuntu 到 GitHub 的 SSH push，结束 API 快照临时路线。
2. 把 universe metadata 扩展到更完整 ETF 与主板池。
3. 把 rebalance frequency、portfolio caps、turnover budget 做成配置化研究参数。
4. 为策略研究增加 walk-forward 与 failure analysis。
5. 再评估 news/sentiment 特征是否进入离线研究层。
6. 只有在 deterministic trading path 稳定后，才讨论实盘券商接入；LLM 仍不进入交易控制路径。

## 7. 本次版本落地记录

本次阶段版本本地已经完成：

- 本地分支：`arch/llm-foundation`
- 本地版本标签：`v2026.04.14-llm-research`
- bundle 备份：最终提交和标签固定后生成，路径以执行输出为准
- bundle 验证：通过 `git bundle verify`
- 单元测试：`54 tests OK`
- smoke：backtest、paper、agent loop、daily pipeline、simulated strategy research 均通过

远端发布状态：

- 原生 SSH push 失败：`git@github.com: Permission denied (publickey)`。
- Ubuntu 环境未检测到 `GITHUB_TOKEN` 或 `GH_TOKEN`，因此 API 快照兜底不能执行。
- GitHub App 当前对 `Chen0207-bit/quant-agent-lab` 只有 `pull` 权限，没有 `push` 权限。
- 远端 `arch/llm-foundation` 分支与 `v2026.04.14-llm-research` tag 当前未发布成功。

恢复远端发布的最短路径：

1. 把 Ubuntu 的 GitHub SSH key 加到有写权限的 GitHub 账号或 deploy key。
2. 在 Ubuntu 运行 `ssh -T git@github.com` 验证。
3. 运行：

```bash
cd /home/fc/projects/quant-agent-lab
git push -u origin arch/llm-foundation
git push origin v2026.04.14-llm-research
```

如果短期内不修 SSH，则在 Ubuntu 设置有写权限的 token 后运行：

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python scripts/git_snapshot_sync.py --branches main,arch/llm-foundation --tag-name v2026.04.14-llm-research --tag-branch arch/llm-foundation
```
