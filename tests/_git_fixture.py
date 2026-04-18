"""Helpers for building tiny throw-away git repos in tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """Run git with deterministic author/committer."""
    base_env = os.environ.copy()
    base_env.update({
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e",
    })
    if env:
        base_env.update(env)
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=base_env,
    ).stdout


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")


def commit_file(
    repo: Path, rel_path: str, content: str,
    *, message: str, date: str,
) -> str:
    """Write content to rel_path, git add, commit with deterministic date.
    Returns the 40-hex commit SHA.
    """
    p = repo / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    git(repo, "add", rel_path)
    git(
        repo, "commit", "-q", "-m", message,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


def rename_file(
    repo: Path, old: str, new: str,
    *, message: str, date: str,
) -> str:
    git(repo, "mv", old, new)
    git(
        repo, "commit", "-q", "-m", message,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


def rewrite_line(
    repo: Path, rel_path: str, new_content: str,
    *, message: str, date: str,
) -> str:
    (repo / rel_path).write_text(new_content, encoding="utf-8")
    git(repo, "add", rel_path)
    git(
        repo, "commit", "-q", "-m", message,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


def _commit(repo: Path, message: str, date: str) -> str:
    git(
        repo, "commit", "-q", "-m", message,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


def checkout_new_branch(repo: Path, name: str, *, from_rev: str = "HEAD") -> None:
    git(repo, "checkout", "-q", "-b", name, from_rev)


def checkout(repo: Path, ref: str) -> None:
    git(repo, "checkout", "-q", ref)


def merge_no_ff(
    repo: Path, branch: str, *, message: str, date: str,
) -> str:
    """Merge `branch` into the current branch with --no-ff."""
    git(
        repo, "merge", "-q", "--no-ff", "-m", message, branch,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


def merge_squash(
    repo: Path, branch: str, *, message: str, date: str,
) -> str:
    """Squash-merge `branch` into the current branch, single commit."""
    git(repo, "merge", "-q", "--squash", branch)
    return _commit(repo, message, date)


def cherry_pick(repo: Path, rev: str, *, date: str) -> str:
    """Cherry-pick `rev` onto the current branch. Returns the new SHA."""
    git(
        repo, "cherry-pick", rev,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


def revert(repo: Path, rev: str, *, date: str) -> str:
    """Revert `rev` with --no-edit. Returns the revert commit SHA."""
    git(
        repo, "revert", "--no-edit", rev,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )
    return git(repo, "rev-parse", "HEAD").strip()


def delete_file(
    repo: Path, rel_path: str, *, message: str, date: str,
) -> str:
    git(repo, "rm", "-q", rel_path)
    return _commit(repo, message, date)


def copy_file(
    repo: Path, src: str, dst: str, *, message: str, date: str,
) -> str:
    """Copy src → dst (content duplicated), commit, return SHA."""
    content = (repo / src).read_text(encoding="utf-8")
    dst_path = repo / dst
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(content, encoding="utf-8")
    git(repo, "add", dst)
    return _commit(repo, message, date)


