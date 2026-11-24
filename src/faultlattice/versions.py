"""run.json 版本与可复算字段采集（spec 第 7 节、NAMING 第 7 节）。

原则：字段拿不到就显式写 None 并在 null_reasons 记录原因，
绝不省略字段，也绝不编造 commit。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from faultlattice.canonical import sha256_hex
from faultlattice.schemas import VersionInfo


def _git_commit(repo_root: Path) -> str | None:
    """取当前 git HEAD；仓库无提交或 git 不可用时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def collect_versions(repo_root: Path, *, host_package_version: str | None) -> VersionInfo:
    repo_root = Path(repo_root)
    null_reasons: dict[str, str] = {}

    commit = _git_commit(repo_root)
    if commit is None:
        null_reasons["faultlattice_commit"] = "仓库尚无提交或 git 不可用"

    lock_path = repo_root / "uv.lock"
    lock_hash: str | None = None
    if lock_path.exists():
        lock_hash = sha256_hex(lock_path.read_bytes())
    else:
        null_reasons["dependency_lock_hash"] = "uv.lock 不存在"

    if host_package_version is None:
        null_reasons["host_package_version"] = "本地受控测试宿主位于仓库内，无独立包版本"

    # M0–M2 不涉及真实模型：model_id / sampling_params 显式为 None
    null_reasons["model_id"] = "M0–M2 不使用真实模型"
    null_reasons["sampling_params"] = "M0–M2 不使用真实模型"
    # in-tree 宿主的源码版本即 faultlattice_commit，不重复登记
    null_reasons["host_commit"] = "本地受控测试宿主位于仓库内，与 faultlattice_commit 相同"

    return VersionInfo(
        faultlattice_commit=commit,
        host_package_version=host_package_version,
        host_commit=None,
        python_version=sys.version.split()[0],
        dependency_lock_hash=lock_hash,
        model_id=None,
        sampling_params=None,
        null_reasons=null_reasons,
    )
