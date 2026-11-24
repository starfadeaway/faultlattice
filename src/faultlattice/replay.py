"""M1 纯轨迹重放与 M2 故障注入重放（spec 第 2 节）。

- M1：使用记录的模型输出、工具调用和工具返回重新执行宿主，
  测试状态恢复与跨代码版本行为；不用于判断真实模型面对新故障的反应。
- M2：固定旧轨迹，只在记录的注入点替换工具返回或异常，
  测试框架处理与跨版本差异。

两种重放都生成新的 run 目录（四件套齐全），源 run 的产物只读不改。
重放任务的 target_layers / 预注册预期继承自源 run 的 run.json——
预注册声明随任务走，不因为重放而重写。
"""

from __future__ import annotations

from pathlib import Path

from faultlattice.errors import ReplayError
from faultlattice.host import HostAdapter
from faultlattice.runner import execute_run, load_manifest
from faultlattice.schemas import ExecutionMode
from faultlattice.trace import read_jsonl


def _rebuild_script(run_dir: Path) -> list[dict]:
    """从源 run 的 steps.jsonl 重建模型输出脚本（tool_call / final_answer 序列）。"""
    steps = read_jsonl(Path(run_dir) / "steps.jsonl")
    script: list[dict] = []
    for step in steps:
        if step.get("event_type") == "tool_call":
            script.append(
                {"tool_call": {"name": step["tool_name"], "args": step.get("arguments", {})}}
            )
        elif step.get("event_type") == "model_output":
            script.append({"final_answer": step.get("content", "")})
    if not script:
        raise ReplayError(f"源 run 中没有可重放的模型输出: {run_dir}")
    return script


def replay_run(
    source_run_dir: Path,
    host: HostAdapter,
    *,
    mode: ExecutionMode,
    runs_root: Path,
    repo_root: Path,
) -> Path:
    """重放一次历史运行，返回新 run 目录。

    mode=M1：不带故障重放；mode=M2：按源 run 的 FaultSpec 重新注入。
    """
    if mode not in (ExecutionMode.M1, ExecutionMode.M2):
        raise ReplayError(f"replay 只支持 M1 / M2，收到: {mode}")

    manifest = load_manifest(source_run_dir)
    # 重放得到的新任务声明：执行模式改为 M1/M2，脚本来自记录而非预注册原文
    task = manifest.task.model_copy(
        update={"mode": mode, "script": _rebuild_script(source_run_dir)}
    )
    if mode is ExecutionMode.M1:
        # 纯轨迹重放：不注入故障
        task = task.model_copy(update={"fault": None})

    return execute_run(task, host, runs_root=runs_root, repo_root=repo_root)
