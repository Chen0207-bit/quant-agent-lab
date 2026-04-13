import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quant_system.devtools.git_snapshot import (
    GitHubSnapshotClient,
    GitSnapshotError,
    create_verified_bundle,
    ensure_clean_worktree,
    tracked_branch_files,
)


class GitSnapshotTest(unittest.TestCase):
    def test_ensure_clean_worktree_accepts_clean_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _init_repo(Path(tmpdir))
            ensure_clean_worktree(repo)

    def test_ensure_clean_worktree_rejects_dirty_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _init_repo(Path(tmpdir))
            (repo / "untracked.txt").write_text("x\n", encoding="utf-8")
            with self.assertRaises(GitSnapshotError):
                ensure_clean_worktree(repo)

    def test_create_verified_bundle_writes_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _init_repo(Path(tmpdir) / "repo")
            bundle_dir = Path(tmpdir) / "bundles"
            bundle = create_verified_bundle(repo, bundle_dir, ("main",))
            self.assertTrue(bundle.exists())
            self.assertEqual(bundle.suffix, ".bundle")

    def test_tracked_branch_files_reads_committed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = _init_repo(Path(tmpdir))
            files = tracked_branch_files(repo, "main")
            self.assertIn("README.md", files)
            self.assertIn("hello", files["README.md"])

    def test_sync_branch_snapshot_creates_missing_remote_branch(self) -> None:
        client = GitHubSnapshotClient(repo_full_name="owner/repo", token="token", api_base="https://example.test")
        with mock.patch("quant_system.devtools.git_snapshot.tracked_branch_files", return_value={"README.md": "hello\n"}):
            with mock.patch.object(client, "get_branch_head_sha", side_effect=[None, "main-parent"]):
                with mock.patch.object(client, "create_tree", return_value="tree-sha"):
                    with mock.patch.object(client, "create_commit", return_value="commit-sha"):
                        with mock.patch.object(client, "create_branch_ref") as create_branch_ref:
                            result = client.sync_branch_snapshot(repo_dir=Path("/tmp/repo"), local_branch="arch/llm-foundation")
        self.assertEqual(result.remote_branch, "arch/llm-foundation")
        self.assertEqual(result.file_count, 1)
        create_branch_ref.assert_called_once_with("arch/llm-foundation", "commit-sha")


    def test_sync_tag_snapshot_creates_annotated_tag_ref(self) -> None:
        client = GitHubSnapshotClient(repo_full_name="owner/repo", token="token", api_base="https://example.test")
        with mock.patch.object(client, "get_tag_ref_sha", return_value=None):
            with mock.patch.object(client, "create_annotated_tag", return_value="tag-sha") as create_annotated_tag:
                with mock.patch.object(client, "create_tag_ref") as create_tag_ref:
                    result = client.sync_tag_snapshot(
                        tag_name="v2026.04.14-llm-research",
                        target_sha="commit-sha",
                        message="release message",
                    )
        self.assertEqual(result.tag_name, "v2026.04.14-llm-research")
        self.assertEqual(result.target_sha, "commit-sha")
        self.assertEqual(result.tag_sha, "tag-sha")
        create_annotated_tag.assert_called_once_with(
            tag_name="v2026.04.14-llm-research",
            target_sha="commit-sha",
            message="release message",
        )
        create_tag_ref.assert_called_once_with("v2026.04.14-llm-research", "tag-sha")

    def test_sync_tag_snapshot_rejects_existing_remote_tag(self) -> None:
        client = GitHubSnapshotClient(repo_full_name="owner/repo", token="token", api_base="https://example.test")
        with mock.patch.object(client, "get_tag_ref_sha", return_value="tag-sha"):
            with self.assertRaises(GitSnapshotError):
                client.sync_tag_snapshot(tag_name="v1", target_sha="commit-sha")



def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=path, check=True, capture_output=True, text=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True)
    return path


if __name__ == "__main__":
    unittest.main()
