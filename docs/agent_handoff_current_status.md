# A 股量化系统当前状态交接文档

更新日期：2026-04-13
项目路径：`/home/fc/projects/quant-agent-lab`
运行环境：Ubuntu `fc@192.168.93.130`
当前阶段：A 股中低频 paper-only MVP，模块化单体，多 Agent 职责边界原型

## 1. 背景与目标

本项目目标是搭建一个可落地、可验证、可迭代的 A 股中低频量化交易系统。当前约束如下：

- 目标市场：A 股。
- 数据源：免费数据优先，MVP 使用 AKShare。
- 交易频率：日线/中低频，不做分钟、Tick、L2。
- 资金规模：约 10 万人民币。
- 当前执行模式：paper trading，不接真实券商 API。
- MVP universe：ETF 优先，主板样本股用于工程链路验证。
- Agent 定位：职责分层和研发协作，不允许 LLM 直接下单或绕过风控。

本项目参考 `ai-quant-book` 第 21 课的多 Agent 教学结构，但没有照搬美股/yfinance 示例。当前实现采用 A 股工程化适配：数据、交易日历、风控、回测/模拟、报告全部围绕 A 股低频场景设计。

## 2. 当前已完成的主链路

当前已经跑通以下链路：

```text
AKShare
 -> 本地 Parquet / DuckDB 数据层
 -> A 股 universe / 真实交易日历
 -> RegimeAgent 市场状态识别
 -> SignalAgent 策略目标仓位生成
 -> Portfolio sizing 目标仓位转订单意图
 -> RiskAgent / RiskEngine 确定性风控审核
 -> ExecutionAgent / PaperBroker 模拟执行
 -> MonitorAgent 日报、JSON、manual_orders.csv、data_sync_report.json
```

这条链路当前由 `scripts/daily_pipeline.py` 串联。它会：

1. 读取 `configs/` 配置。
2. 构建 A 股 MVP universe。
3. 读取或拉取 AKShare 真实交易日历。
4. 将非交易日 `--as-of` 回滚到最近 A 股交易日。
5. 同步指定 universe 的本地 Parquet 数据。
6. 从本地数据运行模块化 Agent loop。
7. 写入 Markdown 日报、JSON 摘要、人工订单 CSV、数据同步报告。

## 3. 已新增或重点修改的文件

### 配置与 universe

- `configs/universe.toml`
  - ETF 样本：`510300`, `510500`, `159915`。
  - 主板工程验证样本：`600000`, `600519`, `601318`, `601888`, `000001`, `000333`, `000651`, `002415`。
  - 继续排除创业板、科创板、北交所等非 MVP 范围前缀。

- `src/quant_system/config/__init__.py`
  - 导出配置加载接口。

- `src/quant_system/config/settings.py`
  - 使用标准库 `tomllib`，没有新增配置框架依赖。
  - 提供：`load_toml`, `load_universe_config`, `load_agent_loop_config`, `load_regime_config`, `load_risk_config`, `load_cost_config`。
  - 定义：`UniverseBucketConfig`, `UniverseConfig`, `AgentLoopConfig`。

- `src/quant_system/data/universe.py`
  - 提供 `build_mvp_universe(config)`。
  - 复用 `classify_symbol` 和 `is_mvp_allowed_instrument`。
  - 过滤创业板、科创板、北交所、ST、停牌、未知板块。

### 交易日历

- `src/quant_system/data/calendar.py`
  - 新增 `TradingCalendar`。
  - `TradingCalendar.from_akshare(cache_dir, start, end)` 从 AKShare 获取真实 A 股交易日历。
  - 缓存路径：`runs/data/calendar/trading_days.parquet`。
  - 不使用“工作日”伪造 A 股交易日。
  - 提供：`is_trading_day(day)`, `previous_trading_day(day)`, `next_trading_day(day)`, `latest_trading_day(end)`。

### Agent loop 与报告

- `src/quant_system/app/main_loop.py`
  - `AgentLoopResult` 新增结构化 `reconcile` 字段。
  - 方便后续 JSON 报告和审计，不需要解析 Markdown。

- `src/quant_system/agents/monitor_agent.py`
  - 保留 `render_daily_summary` 和 `render_daily_json`。
  - 新增 `write_daily_outputs`，统一落盘：`daily_summary.md`, `daily_summary.json`, `manual_orders.csv`, `data_sync_report.json`。
  - JSON 中对 `date/datetime` 做 ISO 格式序列化。

### 日终流水线

- `src/quant_system/app/daily_pipeline.py`
  - 主要应用逻辑，提供 `run_daily_pipeline(...)`。
  - 提供 `DailyPipelineResult` 和 `DailyPipelineError`。
  - 功能：配置读取、交易日历、数据同步、策略构建、Agent loop、报告落盘。
  - 明确限制：当前只支持 `paper` execution mode。

- `scripts/daily_pipeline.py`
  - CLI 入口。
  - 主要参数：

```bash
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py \
  --as-of 2025-01-31 \
  --symbols 510300,510500 \
  --lookback-days 5 \
  --max-retries 2 \
  --retry-backoff-seconds 1
```

## 4. 当前多 Agent 如何协作

当前的多 Agent 是模块化单体中的工程职责分层，不是多个 LLM 运行时互相通信。

```text
DailyPipeline
  -> DataManager 同步/读取行情
  -> TradingCalendar 决定有效 A 股交易日
  -> ModularAgentLoop 统一编排

ModularAgentLoop 内部：
  -> RegimeAgent 判断市场状态
  -> SignalAgent 调用策略并按 regime 权重缩放目标仓位
  -> Portfolio sizing 将目标仓位转换成 OrderIntent
  -> RiskAgent 调用确定性 RiskEngine 审核订单
  -> ExecutionAgent 调用 PaperBroker 做模拟成交
  -> MonitorAgent 生成日报、JSON、manual orders 和同步报告
```

各 Agent 当前职责：

- `RegimeAgent`：输入历史 bars；输出 `RegimeState(regime, confidence, weights, reason)`；当前基于收益、波动率、相关性近似识别 `trending / mean_reverting / crisis / uncertain`。
- `SignalAgent`：输入历史 bars、当前组合、`RegimeState`；输出 `TargetPosition`；调用策略并按 regime 权重缩放目标仓位，不直接生成订单。
- `RiskAgent`：输入 `OrderIntent`、组合快照、行情、instrument 元数据；输出 `RiskDecision`；本质是 `RiskEngine` 的薄封装，拥有 veto 权，LLM/Agent 不能覆盖。
- `ExecutionAgent`：输入风控批准后的订单意图；输出 paper `Order` 和 `Fill`；当前只启用 `PaperBroker`，不接真实券商。
- `MonitorAgent`：输入 regime、targets、risk decision、orders、fills、reconcile、data sync report；输出 Markdown、JSON、manual orders CSV、数据同步报告，不参与交易决策。

## 5. 当前运行验证结果

已通过：

```bash
.venv/bin/python -m compileall -q src tests scripts main.py
```

已通过：

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

结果：27 个测试通过。

已通过 smoke：

```bash
PYTHONPATH=src .venv/bin/python scripts/run_backtest_smoke.py
PYTHONPATH=src .venv/bin/python scripts/paper_run_smoke.py
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_smoke.py
```

已通过真实 AKShare 数据同步：

```bash
PYTHONPATH=src .venv/bin/python scripts/data_sync_akshare.py \
  --start 2025-01-01 \
  --end 2025-01-31 \
  --symbols 510300,510500 \
  --max-retries 2 \
  --retry-backoff-seconds 1
```

结果：`bars_written = 36`, `quality_passed = true`, `symbols_succeeded = 510300,510500`。

已通过从本地 Parquet 跑 Agent loop：

```bash
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_from_data.py \
  --start 2025-01-01 \
  --end 2025-01-31 \
  --symbols 510300,510500 \
  --lookback-days 5
```

已通过新增日终 pipeline：

```bash
PYTHONPATH=src .venv/bin/python scripts/daily_pipeline.py \
  --as-of 2025-01-31 \
  --symbols 510300,510500 \
  --lookback-days 5 \
  --max-retries 2 \
  --retry-backoff-seconds 1
```

注意：`2025-01-31` 位于 A 股春节休市区间，系统按真实交易日历回滚到最近交易日 `2025-01-27`。

生成报告目录：

```text
runs/reports/2025-01-27/
  daily_summary.md
  daily_summary.json
  manual_orders.csv
  data_sync_report.json
```

## 6. 新增测试覆盖

新增测试文件：

- `tests/test_config_universe.py`
  - 验证 `configs/universe.toml` 能被正确读取。
  - 验证 ETF 和主板样本被纳入。
  - 验证 `300/688/8/4` 等非 MVP 前缀被排除。

- `tests/test_trading_calendar.py`
  - 用 fake 日历验证 `is_trading_day`, `previous_trading_day`, `next_trading_day`, `latest_trading_day`。
  - 验证边界情况下明确抛错。

- `tests/test_daily_pipeline.py`
  - 用 fake 数据源和 fake calendar 跑通 pipeline。
  - 验证报告文件生成：`daily_summary.md`, `daily_summary.json`, `manual_orders.csv`, `data_sync_report.json`。

## 7. 当前明确不做的事情

以下内容仍不进入当前 MVP：

- 不接真实券商 API。
- 不做自动实盘下单。
- 不做分钟、Tick、L2。
- 不引入 Qlib、vectorbt、Backtrader、NautilusTrader、VeighNa、Kafka、K8s。
- 不让 LLM/Agent 直接改风控或绕过风控。
- 不把 `manual_orders.csv` 当成自动下单文件，只作为人工检查材料。
- 不将当前样本 universe 视为投资建议，它只是工程链路验证池。

## 8. 给下一个 Agent 的建议任务

建议下一个 Agent 从以下任务继续，不要直接接实盘：

1. 更新 `docs/ubuntu_runbook.md`：加入 `daily_pipeline.py` 的标准运行命令、报告路径说明、失败时排查步骤。
2. 增强日终报告：在 `daily_summary.md` 中加入 symbols 列表、数据同步成功/失败数、manual orders 数量、风控拒单明细、当前持仓摘要。
3. 增加 pipeline 失败场景测试：AKShare 同步失败、calendar 不覆盖目标日期、symbols 包含创业板/科创板/北交所。
4. 改进 universe 元数据：当前 `classify_symbol` 基于代码前缀识别，后续可以接 AKShare 名称、停牌、ST 状态。
5. 加入 5 个交易日 paper 运行检查：统计数据同步、风控、对账、报告完整性。
6. 继续保持 Agent 边界：Research/Validation/Ops Agent 可以提出建议和报告；`RiskEngine`、`PaperBroker`、订单状态、资金持仓不能交给 LLM 自主控制。

## 9. 交接注意事项

- 所有后续代码修改应继续在 Ubuntu：`/home/fc/projects/quant-agent-lab`。
- 不要在 Windows `D:\Project` 里改本项目文件。
- 当前 `.venv` 已可用，优先复用：`.venv/bin/python`。
- 如果 AKShare 网络或字段异常，应失败并报告，不要伪造成功数据。
- 当前报告中的 `manual_orders.csv` 是人工检查材料，不是实盘交易指令。
- 真实 API 实盘不进入当前阶段，至少要先 paper 连续稳定运行 5 个交易日。
