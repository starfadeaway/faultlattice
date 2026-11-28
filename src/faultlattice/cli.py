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


def _host_for(host_name: str):
    """按任务预注册装配宿主；可选依赖只在实际选择对应宿主时导入。"""
    if host_name == "local_controlled":
        from faultlattice.adapters.local import LocalControlledHost

        return LocalControlledHost()
    if host_name == "smolagents":
        from faultlattice.adapters.smolagents import SmolagentsHost

        return SmolagentsHost()
    if host_name == "langgraph":
        from faultlattice.adapters.langgraph import LanggraphHost

        return LanggraphHost()
    from faultlattice.errors import ConfigurationError

    raise ConfigurationError(f"未知宿主: {host_name}")


def _model_for(task):
    """只在 M3 实际运行时装配模型 SDK；密钥不进入任务和产物。"""
    from faultlattice.errors import ConfigurationError

    if task.model is None:
        raise ConfigurationError("M3 任务缺少 model 预注册")
    # 核心目录只校验本次模型；控制台反向复用核心，安装后不依赖仓库根 console。
    from faultlattice.model_catalog import resolve_model_option

    option = resolve_model_option(task.model.model_id)
    if option is None:
        raise ConfigurationError(
            f"M3 需要模型 {task.model.model_id} 的完整 LLM 目录项或兼容默认凭据"
        )
    from faultlattice.adapters.openai_model import OpenAICompatibleModel

    return OpenAICompatibleModel(
        task.model, api_key=option.api_key, base_url=option.base_url
    )


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
    agent_id: Annotated[
        str | None, typer.Option(help="host=external 时使用的已登记接入标识。")
    ] = None,
) -> None:
    """执行 M0 预注册实验或从源轨迹执行 M3 反事实续跑。"""
    from faultlattice.counterfactual import CounterfactualRunner
    from faultlattice.errors import ConfigurationError
    from faultlattice.report import generate_report
    from faultlattice.runner import execute_run, load_task

    def _go() -> Path:
        _load_local_env()
        task = load_task(task_file)
        if task.host == "external":
            if not agent_id:
                raise ConfigurationError("外部任务必须显式提供 --agent-id 并通过登记预检")
            from faultlattice.external_registry import ExternalAgentService

            try:
                task_path = task_file.resolve().relative_to(_repo_root()).as_posix()
            except ValueError as exc:
                raise ConfigurationError("外部任务文件必须位于项目根目录内") from exc
            host, task, _ = ExternalAgentService(_repo_root()).binding(agent_id, task_path)
        else:
            host = _host_for(task.host)
        if task.mode is ExecutionMode.M3:
            run_dir = CounterfactualRunner(
                host,
                _model_for(task),
                runs_root=runs_root,
                repo_root=_repo_root(),
            ).run(task)
        else:
            run_dir = execute_run(task, host, runs_root=runs_root, repo_root=_repo_root())
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
    expected_failure_signal: Annotated[
        bool | None,
        typer.Option(
            "--expected-failure-signal/--no-expected-failure-signal",
            help="仅为缺失该字段的历史运行人工补充预期；会写入新清单留痕。",
        ),
    ] = None,
) -> None:
    """重放一次历史运行（M1 纯轨迹 / M2 故障注入）。"""
    from faultlattice.replay import replay_run
    from faultlattice.report import generate_report
    from faultlattice.runner import load_manifest

    def _go() -> Path:
        host = _host_for(load_manifest(run_dir).task.host)
        new_dir = replay_run(
            run_dir,
            host,
            mode=mode,
            runs_root=runs_root,
            repo_root=_repo_root(),
            expected_failure_signal=expected_failure_signal,
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


@app.command("run-batch")
def run_batch(
    task_files: Annotated[list[Path], typer.Argument(help="一个或多个预注册任务 YAML。")],
    runs_root: Annotated[Path, typer.Option(help="运行产物根目录。")] = Path("runs"),
    report_path: Annotated[
        Path | None, typer.Option("--report", help="批次报告路径；默认在 runs_root 下。")
    ] = None,
) -> None:
    """运行前硬校验全部 A/B 配对，执行批次并生成聚合报告。"""
    from faultlattice.batch import generate_batch_report, validate_ab_tasks
    from faultlattice.report import generate_report
    from faultlattice.runner import execute_run, load_task

    def _preflight() -> list:
        tasks = [load_task(path) for path in task_files]
        validate_ab_tasks(tasks)
        return tasks

    tasks = _handle_errors(_preflight)
    run_dirs: list[Path] = []
    failures = 0
    for task in tasks:
        try:
            run_dir = execute_run(task, _host_for(task.host), runs_root=runs_root, repo_root=_repo_root())
            generate_report(run_dir)
            run_dirs.append(run_dir)
            typer.echo(f"运行完成: {run_dir}")
        except FaultLatticeError as exc:
            # 单个任务失败不中断批次；最终仍以非零退出码报告 Harness 错误。
            failures += 1
            typer.secho(
                f"任务失败 [{type(exc).__name__}] {task.task_id}: {exc}",
                err=True,
                fg=typer.colors.RED,
            )

    if run_dirs:
        output = report_path or runs_root / "batch-report.md"
        _handle_errors(generate_batch_report, run_dirs, output)
        typer.echo(f"批次报告已生成: {output}")
    if failures:
        raise typer.Exit(code=2)
    typer.echo(f"批次完成：{len(run_dirs)} 次运行")


@app.command("batch-report")
def batch_report(
    run_dirs: Annotated[list[Path], typer.Argument(help="一个或多个已有 run 目录。")],
    output_path: Annotated[
        Path, typer.Option("--output", help="批次报告输出路径。")
    ] = Path("reports/batch-report.md"),
) -> None:
    """只读原始 run 产物，生成跨运行批次聚合报告。"""
    from faultlattice.batch import generate_batch_report

    path = _handle_errors(generate_batch_report, run_dirs, output_path)
    typer.echo(f"批次报告已生成: {path}")


@app.command("batch-verify")
def batch_verify(
    run_dirs: Annotated[list[Path], typer.Argument(help="批次包含的全部 run 目录。")],
    report_path: Annotated[
        Path, typer.Option("--report", help="待复算的批次报告。")
    ] = Path("reports/batch-report.md"),
) -> None:
    """从原始产物独立重算批次报告；不一致时退出码为 1。"""
    from faultlattice.batch import verify_batch_report

    problems = _handle_errors(verify_batch_report, report_path, run_dirs)
    if problems:
        for problem in problems:
            typer.secho(f"复算失败: {problem}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.echo(f"批次复算一致: {report_path}")


def _load_local_env() -> None:
    """从可安装核心包加载 .env；控制台脚本不依赖仓库根模块。"""
    from faultlattice.env import load_env

    load_env(_repo_root() / ".env")


@app.command("index-runs")
def index_runs(
    runs_root: Annotated[Path, typer.Option(help="原始运行产物根目录。")] = Path("runs"),
) -> None:
    """从完整四件套重建 MySQL 结构索引；不启动或停止数据库服务。"""
    from faultlattice.indexing import collect_run_records

    def _go() -> int:
        _load_local_env()
        from faultlattice.adapters.mysql_index import PyMySQLRunIndex

        records = collect_run_records(runs_root)
        return PyMySQLRunIndex.from_env().rebuild(records)

    count = _handle_errors(_go)
    typer.echo(f"MySQL 结构索引重建完成：{count} 次运行")


@app.command("similarity-build")
def similarity_build(
    runs_root: Annotated[Path, typer.Option(help="原始运行产物根目录。")] = Path("runs"),
    index_root: Annotated[
        Path, typer.Option(help="LanceDB 派生索引目录。")
    ] = Path("runs/_index/lancedb"),
) -> None:
    """使用冻结的 embedding 契约重建 LanceDB 相似故障索引。"""
    from faultlattice.indexing import collect_run_records

    def _go() -> int:
        _load_local_env()
        from faultlattice.adapters.lance_similarity import LanceSimilarityStore
        from faultlattice.adapters.openai_embedding import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.from_env()
        records = collect_run_records(runs_root)
        store = LanceSimilarityStore(index_root, provider.spec)
        return store.rebuild(records, provider)

    count = _handle_errors(_go)
    typer.echo(f"LanceDB 相似索引重建完成：{count} 次运行；目录：{index_root}")


@app.command("similarity-search")
def similarity_search(
    query: Annotated[str, typer.Argument(help="故障、任务或判定描述。")],
    index_root: Annotated[
        Path, typer.Option(help="已构建的 LanceDB 索引目录。")
    ] = Path("runs/_index/lancedb"),
    limit: Annotated[int, typer.Option(help="返回 1–100 条结果。")] = 5,
) -> None:
    """检索相似运行；score 是 cosine similarity，不是实验成功率。"""
    def _go() -> list:
        _load_local_env()
        from faultlattice.adapters.lance_similarity import LanceSimilarityStore
        from faultlattice.adapters.openai_embedding import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider.from_env()
        store = LanceSimilarityStore(index_root, provider.spec)
        return store.search(query, provider, limit=limit)

    hits = _handle_errors(_go)
    if not hits:
        typer.echo("没有找到相似运行；请先确认索引已构建且包含运行记录")
        return
    for hit in hits:
        typer.echo(
            f"{hit.score:.6f}\t{hit.run_id}\t{hit.host} / {hit.mode} / "
            f"{hit.fault_type or 'N/A'} / {hit.surface_as or 'N/A'}"
        )


@app.command("quality-gate")
def quality_gate(
    current_runs: Annotated[
        list[Path], typer.Argument(help="当前待验收的一个或多个 run 目录。")
    ],
    baseline: Annotated[
        Path, typer.Option("--baseline", help="版本化 baseline YAML；运行路径相对仓库根。")
    ],
    output: Annotated[
        Path, typer.Option("--output", help="门禁 Markdown 报告。")
    ] = Path("runs/_quality/quality-gate.md"),
) -> None:
    """配对原始四件套并拒绝登记的行为或产物回归；不替代测试和静态检查。"""
    from faultlattice.quality import (
        evaluate_quality_gate,
        generate_quality_gate_report,
        load_quality_baseline,
    )

    name, baseline_runs = _handle_errors(load_quality_baseline, baseline, _repo_root())
    result = _handle_errors(evaluate_quality_gate, name, baseline_runs, current_runs)
    _handle_errors(generate_quality_gate_report, result, output)
    typer.echo(f"门禁报告: {output}")
    if not result.passed:
        for violation in result.violations:
            typer.secho(
                f"回归 [{violation.code}]: {violation.message}", err=True, fg=typer.colors.RED
            )
        raise typer.Exit(code=1)
    typer.echo(
        f"门禁通过：{result.matched_coordinates} 个完整坐标；不替代 pytest / Ruff / Pyright"
    )
