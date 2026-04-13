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
    parser.add_argument("--tag-name", default="", help="Optional annotated tag to create on the remote snapshot commit")
    parser.add_argument("--tag-branch", default="arch/llm-foundation", help="Remote branch snapshot commit to tag")
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
    tag_result = None
    if not args.skip_remote:
        client = GitHubSnapshotClient.from_env(repo_full_name=args.repo)
        branch_commits = {}
        for branch in branches:
            result = client.sync_branch_snapshot(repo_dir=repo_dir, local_branch=branch)
            remote_results.append(asdict(result))
            branch_commits[result.remote_branch] = result.commit_sha
        if args.tag_name:
            target_sha = branch_commits.get(args.tag_branch)
            if target_sha is None:
                raise SystemExit("tag branch must be included in --branches for remote snapshot tagging")
            tag_name = _next_available_tag_name(client, args.tag_name)
            tag_result = asdict(
                client.sync_tag_snapshot(
                    tag_name=tag_name,
                    target_sha=target_sha,
                    message=f"snapshot release {tag_name} from local {args.tag_branch}",
                )
            )

    print(
        json.dumps(
            {
                "repo": args.repo,
                "bundle_path": str(bundle_path),
                "branches": list(branches),
                "remote_results": remote_results,
                "tag_result": tag_result,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )


def _next_available_tag_name(client: GitHubSnapshotClient, preferred: str) -> str:
    if client.get_tag_ref_sha(preferred) is None:
        return preferred
    index = 1
    while True:
        candidate = f"{preferred}.{index}"
        if client.get_tag_ref_sha(candidate) is None:
            return candidate
        index += 1


if __name__ == "__main__":
    main()
