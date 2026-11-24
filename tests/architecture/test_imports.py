"""AST 依赖方向检查（spec 第 8 节）。

核心模块（src/faultlattice 下除 adapters/ 与 cli.py 以外的所有模块）
禁止导入：

- faultlattice.adapters（core 不依赖 adapters）
- console（平台层）
- fastapi / openai / smolagents / langchain / langgraph（外部框架与 SDK）

cli.py 是 core 与 adapters 的装配点，豁免本检查；
adapters/ 允许依赖 core，不在被检集合内。
"""

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = (
    "faultlattice.adapters",
    "console",
    "fastapi",
    "openai",
    "smolagents",
    "langchain",
    "langgraph",
)

SRC_DIR = Path(__file__).parent.parent.parent / "src" / "faultlattice"


def _core_modules() -> list[Path]:
    modules = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        rel = path.relative_to(SRC_DIR)
        if rel.parts[0] == "adapters":
            continue  # adapters 是允许依赖 core 的一侧
        if rel.name == "cli.py":
            continue  # 装配点豁免
        modules.append(path)
    return modules


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_core_modules_exist() -> None:
    assert _core_modules(), "未找到任何核心模块，检查 SRC_DIR 配置"


def test_core_does_not_import_forbidden() -> None:
    violations: list[str] = []
    for path in _core_modules():
        for name in _imports_of(path):
            if name == "faultlattice.adapters" or name.startswith("faultlattice.adapters."):
                violations.append(f"{path.name}: import {name}")
            elif name.split(".")[0] in {
                p.split(".")[0] for p in FORBIDDEN_PREFIXES if not p.startswith("faultlattice")
            }:
                violations.append(f"{path.name}: import {name}")
    assert not violations, "核心模块违反依赖方向禁令：\n" + "\n".join(violations)
