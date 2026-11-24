"""FaultLattice CLI 入口。

阶段 0：--help / --version；阶段 2 起提供 run / replay / report / verify。

退出码约定（NAMING 第 10 节）：
- 实验成功执行（即使发现 silent_failure）：0；
- Harness 自身错误（配置 / adapter / 轨迹 / 写入）：非零；
- verify 复算失败：非零。

CLI 是 core 与 adapters 的装配点：只有这里允许同时 import 两边。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from faultlattice import __version__
from faultlattice.errors import FaultLatticeError
from faultlattice.schemas import ExecutionMode

app = typer.Typer(
    name="faultlattice",
    help="Agent Reliability Harness & Evaluation Platform.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"faultlattice {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="显示版本号并退出。", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """FaultLattice 命令行入口。"""


def _repo_root() -> Path:
    # 仓库根 = 包的曾祖目录（src/faultlattice/cli.py → 根）。
    # 安装为站点包时回退到当前目录；uv run 场景下两者一致。
    here = Path(__file__).resolve()
    root = here.parents[2]
    return root if (root / "pyproject.toml").exists() else Path.cwd()


def _local_host():
    from faultlattice.adapters.local import LocalControlledHost

    return LocalControlledHost()


def _handle_errors(func, *args, **kwargs):
    """边界统一处理 Harness 异常：人类可读错误 + 非零退出码。"""
    try:
        return func(*args, **kwargs)
    except FaultLatticeError as exc:
        typer.secho(f"错误 [{type(exc).__name__}]: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from None


@app.command()
def run(
    task_file: Annotated[Path, typer.Argument(help="预注册任务定义文件（YAML）。")],
    runs_root: Annotated[Path, typer.Option(help="运行产物根目录。")] = Path("runs"),
) -> None:
    """执行一次故障注入实验（M0 预设脚本）。"""
    from faultlattice.report import generate_report
    from faultlattice.runner import execute_run, load_task

    def _go() -> Path:
        task = load_task(task_file)
        run_dir = execute_run(task, _local_host(), runs_root=runs_root, repo_root=_repo_root())
        generate_report(run_dir)
        return run_dir

    run_dir = _handle_errors(_go)
    typer.echo(f"运行完成: {run_dir}")
    typer.echo(f"复算验证: faultlattice verify {run_dir}")


@app.command()
def replay(
    run_dir: Annotated[Path, typer.Argument(help="源 run 目录。")],
    mode: Annotated[ExecutionMode, typer.Option(help="重放模式：M1 / M2。")] = ExecutionMode.M1,
    runs_root: Annotated[Path, typer.Option(help="运行产物根目录。")] = Path("runs"),
) -> None:
    """重放一次历史运行（M1 纯轨迹 / M2 故障注入）。"""
    from faultlattice.replay import replay_run
    from faultlattice.report import generate_report

    def _go() -> Path:
        new_dir = replay_run(
            run_dir, _local_host(), mode=mode, runs_root=runs_root, repo_root=_repo_root()
        )
        generate_report(new_dir)
        return new_dir

    new_dir = _handle_errors(_go)
    typer.echo(f"重放完成（{mode}）: {new_dir}")


@app.command()
def report(
    run_dir: Annotated[Path, typer.Argument(help="run 目录。")],
) -> None:
    """只根据原始产物重新生成 report.md。"""
    from faultlattice.report import generate_report

    path = _handle_errors(generate_report, run_dir)
    typer.echo(f"报告已生成: {path}")


@app.command()
def verify(
    run_dir: Annotated[Path, typer.Argument(help="run 目录。")],
) -> None:
    """独立重算报告数字并与 report.md 比对。复算失败退出码非零。"""
    from faultlattice.report import verify_report

    problems = _handle_errors(verify_report, run_dir)
    if problems:
        for p in problems:
            typer.secho(f"复算失败: {p}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.echo(f"复算一致: {run_dir}")
