"""本地外部源码和临时验收资料不得混入项目检查或公开提交。"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_local_only_directories_are_excluded_from_ruff() -> None:
    config = tomllib.loads((ROOT / "ruff.toml").read_text(encoding="utf-8"))

    assert {".verify", "external_projects"} <= set(config["extend-exclude"])


def test_local_only_directories_are_ignored_by_git() -> None:
    rules = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }

    assert {".verify/", "external_projects/"} <= rules
