"""Helpers for local bundle creation and remote GitHub tree snapshots."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GitSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BranchSnapshotResult:
    branch: str
    remote_branch: str
    file_count: int
    commit_sha: str


def ensure_clean_worktree(repo_dir: Path | str) -> None:
    output = _git_output(Path(repo_dir), "status", "--short")
    if output.strip():
        raise GitSnapshotError("working tree is not clean; commit or discard changes before snapshot sync")


def create_verified_bundle(repo_dir: Path | str, bundle_dir: Path | str, branches: tuple[str, ...]) -> Path:
    repository = Path(repo_dir)
    target_dir = Path(bundle_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_path = target_dir / f"quant-agent-lab-{stamp}.bundle"
    _git_output(repository, "bundle", "create", str(bundle_path), *branches)
    _git_output(repository, "bundle", "verify", str(bundle_path))
    return bundle_path


def tracked_branch_files(repo_dir: Path | str, branch: str) -> dict[str, str]:
    repository = Path(repo_dir)
    listing = _git_output(repository, "ls-tree", "-r", "--name-only", branch)
    files: dict[str, str] = {}
    for path in [line.strip() for line in listing.splitlines() if line.strip()]:
        content = _git_bytes(repository, "show", f"{branch}:{path}")
        try:
            files[path] = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitSnapshotError(f"non-UTF-8 tracked file is not supported by snapshot sync: {path}") from exc
    if not files:
        raise GitSnapshotError(f"branch {branch} has no tracked files")
    return files


class GitHubSnapshotClient:
    def __init__(self, *, repo_full_name: str, token: str, api_base: str = "https://api.github.com") -> None:
        if "/" not in repo_full_name:
            raise ValueError("repo_full_name must be in owner/name form")
        self.repo_full_name = repo_full_name
        self.token = token
        self.api_base = api_base.rstrip("/")

    @classmethod
    def from_env(cls, *, repo_full_name: str, api_base: str = "https://api.github.com") -> "GitHubSnapshotClient":
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise GitSnapshotError("missing GITHUB_TOKEN or GH_TOKEN for remote snapshot sync")
        return cls(repo_full_name=repo_full_name, token=token, api_base=api_base)

    def sync_branch_snapshot(
        self,
        *,
        repo_dir: Path | str,
        local_branch: str,
        remote_branch: str | None = None,
        parent_branch: str = "main",
    ) -> BranchSnapshotResult:
        branch_name = remote_branch or local_branch
        files = tracked_branch_files(repo_dir, local_branch)
        branch_head = self.get_branch_head_sha(branch_name)
        parent_sha = branch_head or self.get_branch_head_sha(parent_branch)
        tree_sha = self.create_tree(files)
        commit_sha = self.create_commit(
            message=f"snapshot: sync {branch_name} from local {local_branch}",
            tree_sha=tree_sha,
            parent_shas=tuple([parent_sha] if parent_sha else []),
        )
        if branch_head:
            self.update_branch_ref(branch_name, commit_sha)
        else:
            self.create_branch_ref(branch_name, commit_sha)
        return BranchSnapshotResult(
            branch=local_branch,
            remote_branch=branch_name,
            file_count=len(files),
            commit_sha=commit_sha,
        )

    def get_branch_head_sha(self, branch: str) -> str | None:
        ref = quote(f"heads/{branch}", safe="")
        try:
            payload = self._request_json("GET", f"/repos/{self.repo_full_name}/git/ref/{ref}")
        except GitSnapshotError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        if not isinstance(payload, dict):
            raise GitSnapshotError("unexpected ref payload from GitHub")
        obj = payload.get("object")
        if not isinstance(obj, dict) or "sha" not in obj:
            raise GitSnapshotError("ref payload missing object.sha")
        return str(obj["sha"])

    def create_tree(self, files: dict[str, str]) -> str:
        payload = {
            "tree": [
                {
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "content": content,
                }
                for path, content in sorted(files.items())
            ]
        }
        response = self._request_json("POST", f"/repos/{self.repo_full_name}/git/trees", payload)
        if not isinstance(response, dict) or "sha" not in response:
            raise GitSnapshotError("tree creation did not return a sha")
        return str(response["sha"])

    def create_commit(self, *, message: str, tree_sha: str, parent_shas: tuple[str, ...]) -> str:
        payload: dict[str, Any] = {
            "message": message,
            "tree": tree_sha,
            "parents": list(parent_shas),
        }
        response = self._request_json("POST", f"/repos/{self.repo_full_name}/git/commits", payload)
        if not isinstance(response, dict) or "sha" not in response:
            raise GitSnapshotError("commit creation did not return a sha")
        return str(response["sha"])

    def create_branch_ref(self, branch: str, commit_sha: str) -> None:
        payload = {"ref": f"refs/heads/{branch}", "sha": commit_sha}
        self._request_json("POST", f"/repos/{self.repo_full_name}/git/refs", payload)

    def update_branch_ref(self, branch: str, commit_sha: str) -> None:
        ref = quote(f"heads/{branch}", safe="")
        payload = {"sha": commit_sha, "force": True}
        self._request_json("PATCH", f"/repos/{self.repo_full_name}/git/refs/{ref}", payload)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.api_base}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "quant-agent-lab-git-snapshot",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urlopen(request) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitSnapshotError(f"GitHub API request failed: HTTP {exc.code} {detail}") from exc
        if not body:
            return None
        return json.loads(body)


def _git_output(repo_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _git_bytes(repo_dir: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=False,
    )
    return result.stdout
