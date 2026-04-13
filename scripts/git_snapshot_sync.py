"""Create a verified bundle and optionally sync remote GitHub branch snapshots."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from quant_system.devtools.git_snapshot import (
    GitHubSnapshotClient,
    create_verified_bundle,
    ensure_clean_worktree,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a local git bundle and refresh remote GitHub snapshots.")
    parser.add_argument("--repo", default="Chen0207-bit/quant-agent-lab", help="GitHub repo in owner/name form")
    parser.add_argument("--branches", default="main,arch/llm-foundation", help="Comma-separated local branches to snapshot")
    parser.add_argument("--bundle-dir", default="/home/fc/git-backups", help="Bundle output directory")
    parser.add_argument("--skip-remote", action="store_true", help="Only create a local verified bundle")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_dir = Path(__file__).resolve().parents[1]
    branches = tuple(branch.strip() for branch in args.branches.split(",") if branch.strip())
    if not branches:
        raise SystemExit("no branches selected")

    ensure_clean_worktree(repo_dir)
    bundle_path = create_verified_bundle(repo_dir, args.bundle_dir, branches)
    remote_results = []
    if not args.skip_remote:
        client = GitHubSnapshotClient.from_env(repo_full_name=args.repo)
        for branch in branches:
            remote_results.append(asdict(client.sync_branch_snapshot(repo_dir=repo_dir, local_branch=branch)))

    print(
        json.dumps(
            {
                "repo": args.repo,
                "bundle_path": str(bundle_path),
                "branches": list(branches),
                "remote_results": remote_results,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
