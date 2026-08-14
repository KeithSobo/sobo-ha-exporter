"""Git client wrapper for SSH operations with strict host key checking."""

import logging
import os
import subprocess
from pathlib import Path

from app.github.host_key import ensure_pinned_known_hosts

logger = logging.getLogger(__name__)


class GitClientError(Exception):
    """Raised when a Git command or host verification fails."""

    pass


def validate_branch_name(branch: str) -> bool:
    """Validate Git branch ref format using git check-ref-format --branch.

    Args:
        branch: Branch string to validate.

    Returns:
        True if valid Git branch ref format, False otherwise.
    """
    if not branch or not isinstance(branch, str):
        return False
    if ".." in branch or branch.startswith("/") or branch.endswith("/"):
        return False
    try:
        res = subprocess.run(
            ["git", "check-ref-format", "--branch", branch],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


class GitClient:
    """Subprocess Git wrapper configured with SSH deploy key and host verification."""

    def __init__(
        self,
        repo_dir: Path | str,
        private_key_path: Path | str,
        known_hosts_path: Path | str | None = None,
    ):
        self.repo_dir = Path(repo_dir)
        self.private_key_path = Path(private_key_path)
        self.known_hosts_path = (
            Path(known_hosts_path)
            if known_hosts_path
            else self.private_key_path.parent / "known_hosts"
        )
        self._ensure_known_hosts()

    def _ensure_known_hosts(self) -> None:
        """Verify known_hosts contains pinned official GitHub host key."""
        ensure_pinned_known_hosts(self.known_hosts_path)
        content = self.known_hosts_path.read_text(encoding="utf-8", errors="ignore").strip()
        if "ssh-ed25519" not in content or "github.com" not in content:
            raise GitClientError(
                f"Invalid or unexpected SSH host key content in {self.known_hosts_path}."
            )

    def _get_env(self) -> dict[str, str]:
        """Build environment dict enforcing SSH command with private key and strict host check."""
        env = os.environ.copy()
        ssh_cmd = (
            f"ssh -i '{self.private_key_path}' "
            f"-o UserKnownHostsFile='{self.known_hosts_path}' "
            f"-o StrictHostKeyChecking=yes"
        )
        env["GIT_SSH_COMMAND"] = ssh_cmd
        return env

    def run_git(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        """Execute a git command via subprocess.

        Args:
            args: Git command arguments.
            cwd: Working directory (defaults to self.repo_dir).

        Returns:
            CompletedProcess result.
        """
        target_cwd = cwd or self.repo_dir
        cmd = ["git", *args]
        try:
            res = subprocess.run(
                cmd,
                cwd=target_cwd,
                env=self._get_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            return res
        except Exception as e:
            raise GitClientError(f"Failed to execute git {' '.join(args)}: {e}") from e

    def run_git_checked(
        self, args: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Execute git command and raise GitClientError if exit code is non-zero."""
        res = self.run_git(args, cwd=cwd)
        if res.returncode != 0:
            err_msg = res.stderr.strip() if res.stderr else res.stdout.strip()
            sanitized_err = err_msg.replace(str(self.private_key_path), "[PRIVATE_KEY_PATH]")
            cmd_str = " ".join(args)
            raise GitClientError(
                f"Git command 'git {cmd_str}' failed (exit code {res.returncode}): {sanitized_err}"
            )
        return res

    def test_connection(self, remote_url: str) -> bool:
        """Test SSH connection to remote Git repository."""
        res = self.run_git(["ls-remote", remote_url], cwd=self.private_key_path.parent)
        return res.returncode == 0

    def clone_repository(self, remote_url: str, branch: str = "main") -> None:
        """Clone remote repository into self.repo_dir safely."""
        self.repo_dir.parent.mkdir(parents=True, exist_ok=True)
        res = self.run_git(
            ["clone", "-b", branch, remote_url, str(self.repo_dir)],
            cwd=self.repo_dir.parent,
        )
        if res.returncode != 0:
            res_fallback = self.run_git(
                ["clone", remote_url, str(self.repo_dir)],
                cwd=self.repo_dir.parent,
            )
            if res_fallback.returncode != 0:
                sanitized_err = res_fallback.stderr.strip().replace(
                    str(self.private_key_path), "[PRIVATE_KEY_PATH]"
                )
                raise GitClientError(f"Clone failed: {sanitized_err}")

    def fetch_and_update(self, branch: str = "main") -> None:
        """Fetch remote and safely update or track branch using fast-forward only."""
        self.run_git_checked(["fetch", "origin"])

        res_local = self.run_git(["branch", "--list", branch])
        local_exists = bool(res_local.stdout.strip())

        if local_exists:
            self.run_git_checked(["checkout", branch])
        else:
            res_remote = self.run_git(["branch", "-r", "--list", f"origin/{branch}"])
            remote_exists = bool(res_remote.stdout.strip())
            if remote_exists:
                self.run_git_checked(["checkout", "-b", branch, f"origin/{branch}"])
            else:
                self.run_git_checked(["checkout", "-b", branch])

        res_remote_check = self.run_git(["branch", "-r", "--list", f"origin/{branch}"])
        if res_remote_check.stdout.strip():
            self.run_git_checked(["pull", "--ff-only", "origin", branch])

    def configure_author(self, name: str, email: str) -> None:
        """Set local repo git author identity."""
        self.run_git_checked(["config", "user.name", name])
        self.run_git_checked(["config", "user.email", email])

    def get_porcelain_status(self) -> list[str]:
        """Retrieve lines from git status --porcelain with error checking."""
        res = self.run_git_checked(["status", "--porcelain"])
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    def restore_file(self, file_rel_path: str) -> None:
        """Restore file in both index and working tree with error checking."""
        res_restore = self.run_git(["restore", "--staged", "--worktree", file_rel_path])
        if res_restore.returncode != 0:
            # Fallback for older Git versions
            self.run_git_checked(["checkout", "HEAD", "--", file_rel_path])
            self.run_git_checked(["reset", "HEAD", file_rel_path])

    def commit_and_push(self, message: str, branch: str = "main") -> tuple[bool, str]:
        """Stage all changes, commit, and push to origin without force.

        Restores timestamp-only metadata changes in both index and working tree.
        Raises GitClientError on commit or push failure.

        Args:
            message: Commit message.
            branch: Target branch.

        Returns:
            Tuple of (True, commit_hash) on push, or (False, "no_changes") if no changes exist.

        Raises:
            GitClientError: On commit or push failure.
        """
        lines = self.get_porcelain_status()
        if not lines:
            return False, "no_changes"

        modified_files = [line.split()[-1].replace("\\", "/") for line in lines]

        # Check if ONLY metadata/export-info.json was changed
        if set(modified_files) == {"metadata/export-info.json"}:
            self.restore_file("metadata/export-info.json")
            remaining = self.get_porcelain_status()
            if not remaining:
                return False, "no_changes"

        # Stage all changes
        self.run_git_checked(["add", "-A"])

        # Verify staged changes using git diff --cached --quiet
        res_diff = self.run_git(["diff", "--cached", "--quiet"])
        if res_diff.returncode == 0:
            return False, "no_changes"
        elif res_diff.returncode != 1:
            err_msg = res_diff.stderr.strip() if res_diff.stderr else res_diff.stdout.strip()
            raise GitClientError(
                f"git diff --cached failed (exit code {res_diff.returncode}): {err_msg}"
            )

        self.run_git_checked(["commit", "-m", message])

        res_hash = self.run_git_checked(["rev-parse", "--short", "HEAD"])
        commit_hash = res_hash.stdout.strip()

        # Attempt push
        res_push = self.run_git(["push", "origin", branch])
        if res_push.returncode != 0:
            res_push_u = self.run_git(["push", "-u", "origin", branch])
            if res_push_u.returncode != 0:
                san_err = res_push_u.stderr.strip().replace(
                    str(self.private_key_path), "[PRIVATE_KEY_PATH]"
                )
                raise GitClientError(f"Push to origin/{branch} failed: {san_err}")

        return True, commit_hash
