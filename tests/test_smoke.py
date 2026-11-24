"""阶段 0 smoke tests：验证包可导入、最小 CLI 可用。

避免空测试目录导致 CI 出现 "no tests ran"。
"""

from typer.testing import CliRunner

import faultlattice
from faultlattice.cli import app

runner = CliRunner()


def test_package_importable() -> None:
    assert faultlattice.__version__


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "faultlattice" in result.output.lower() or "Usage" in result.output


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert faultlattice.__version__ in result.output
