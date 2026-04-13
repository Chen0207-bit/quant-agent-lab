# Git Workflow and Rollback Guide

This document defines the git workflow for `/home/fc/projects/quant-agent-lab`.
The goal is to let the architecture thread and the strategy thread move in parallel,
with small commits, predictable merges, and safe rollback.

## Current state

- Local repo: initialized
- Default branch: `main`
- Architecture branch: `arch/llm-foundation`
- Remote: `git@github.com:Chen0207-bit/quant-agent-lab.git`
- External blocker: Ubuntu still cannot push to GitHub over SSH; current error is
  `Permission denied (publickey)`.
- Remote nuance: the GitHub repo was bootstrapped with a README-only `main` commit via API,
  so the first real sync from local `main` should use `git push --force-with-lease origin main`.

## SSH key prerequisite

The Ubuntu host already has a public key at:

```text
~/.ssh/id_ed25519.pub
```

Current public key:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAPb919CE2FC+HTrKkRtUO4BfLuFOhCwP2xeeufLxBOT 196518943+Chen0207-bit@users.noreply.github.com
```

Add that key to the GitHub account or to a write-enabled deploy key, then verify:

```bash
ssh -T git@github.com
cd /home/fc/projects/quant-agent-lab
git push -u origin main
git push -u origin arch/llm-foundation
```

If `Permission denied (publickey)` still appears, remote backup is still blocked.

## Branch policy

- `main`: stable baseline only
- `arch/llm-foundation`: architecture, orchestration, LLM read-only layer, docs
- `strategy/<topic>`: strategy, factors, diagnostics, parameter experiments

## File ownership

Strategy thread should mostly change:

- `src/quant_system/features/*`
- `src/quant_system/strategies/*`
- `configs/strategy.toml`
- `tests/*strategy*`
- strategy diagnostics logic

Architecture thread should mostly change:

- `src/quant_system/agents/*`
- `src/quant_system/app/*`
- `src/quant_system/llm/*`
- `configs/llm.toml`
- `docs/*`
- report and audit artifact logic

Both threads should avoid changing unless necessary:

- `src/quant_system/risk/engine.py`
- `src/quant_system/execution/paper.py`
- `src/quant_system/data/calendar.py`

## Minimal change loop

```bash
cd /home/fc/projects/quant-agent-lab
git checkout <your-branch>
.venv/bin/python -m compileall -q src tests scripts main.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
git status
git add <changed-files>
git commit -m "<type>: <message>"
git push -u origin <your-branch>
```

Recommended commit granularity:

- one feature per commit
- one test block per commit
- one docs update per commit

## Rollback

Prefer `git revert`, not `git reset --hard`, for shared history.

Inspect history:

```bash
git log --oneline --decorate -n 20
```

Revert a single commit:

```bash
git revert <commit_sha>
```

Temporarily inspect an old revision:

```bash
git checkout <commit_sha>
```

Return to the working branch:

```bash
git checkout arch/llm-foundation
```

## Merge order

1. Stabilize the architecture branch.
2. Merge the strategy branch after interface alignment.
3. Run full regression before merge.
4. Run `daily_pipeline.py` once on `main` after merge.
