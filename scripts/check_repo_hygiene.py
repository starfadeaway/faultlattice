"""仓库卫生检查：CI 与本地共用。

检查项：
1. .gitignore 必须包含运行产物与凭据的关键规则（含 runs/_sample 例外）；
2. 真实 .env 不得被 git 跟踪；
3. runs/ 下除 _sample/ 外不应有需要提交的内容（有也只是本地产物，提醒即可）。

退出码：全部通过 0，任一失败 1。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_GITIGNORE_RULES = ["runs/*", "!runs/_sample/", "!runs/_sample/**", ".env"]


def check_gitignore() -> list[str]:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines()}
    return [f".gitignore 缺少规则: {rule}" for rule in REQUIRED_GITIGNORE_RULES if rule not in lines]


def check_env_not_tracked() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", ".env"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []  # git 不可用时跳过（本地首次初始化前）
    if result.returncode != 0:
        return []
    if result.stdout.strip():
        return [".env 被 git 跟踪，必须移除并轮换其中凭据"]
    return []


def check_runs_dir() -> list[str]:
    """runs/ 下被 git 跟踪的内容只能位于 _sample/（本地产物被 gitignore，不算违规）。"""
    runs = REPO_ROOT / "runs"
    if not runs.exists():
        return []
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", "runs"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    problems = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if rel and not rel.startswith("runs/_sample/"):
            problems.append(f"runs/ 下被跟踪的非 _sample 内容: {rel}（应只提交公开样例）")
    return problems


def main() -> int:
    problems = check_gitignore() + check_env_not_tracked() + check_runs_dir()
    if problems:
        for p in problems:
            print(f"[FAIL] {p}")
        return 1
    print("仓库卫生检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
