# Ubuntu Runbook

Target directory for this implementation:

```text
/home/fc/projects/quant-agent-lab
```

## Offline verification

These commands require only the Python standard library and the local source tree:

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 scripts/data_sync_smoke.py
PYTHONPATH=src python3 scripts/run_backtest_smoke.py
PYTHONPATH=src python3 scripts/paper_run_smoke.py
PYTHONPATH=src python3 scripts/run_agent_loop_smoke.py
PYTHONPATH=src python3 scripts/report_gen_smoke.py
```

## Dependency setup

Preferred project-local setup:

```bash
cd /home/fc/projects/quant-agent-lab
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# If the default PyPI route is slow from this host:
.venv/bin/python -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --retries 2
```

If Ubuntu lacks `ensurepip`/`python3-venv`, stop and install the system venv package manually outside the trading app change set. Do not install dependencies into system Python.

## Real AKShare data path

After `.venv` is ready:

```bash
cd /home/fc/projects/quant-agent-lab
PYTHONPATH=src .venv/bin/python scripts/data_sync_akshare.py --start 2025-01-01 --end 2025-01-31 --symbols 510300,510500 --max-retries 2 --retry-backoff-seconds 1
PYTHONPATH=src .venv/bin/python scripts/run_agent_loop_from_data.py --start 2025-01-01 --end 2025-01-31 --symbols 510300,510500 --lookback-days 5
```

## Production-style directories

```text
/opt/quant-a-share/app
/var/lib/quant-a-share
/etc/quant-a-share/config
/var/log/quant-a-share
/var/backups/quant-a-share
```

Do not connect a live broker until the paper run and reconciliation checks are stable for at least five trading days.
