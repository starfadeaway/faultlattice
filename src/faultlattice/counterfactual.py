"""M3 反事实续跑编排：读取源轨迹中的目标调用契约，再建立真实模型前缀。

源 run 永远只读。M0 的预设输出只定义目标任务、目标工具参数和故障坐标，
不冒充思考模型的真实前缀。宿主先让所选模型现场生成完全匹配的目标调用，
保存其原始 reasoning_content，再注入故障并从同一消息上下文继续生成。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from faultlattice.errors import ConfigurationError, ReplayError
from faultlattice.host import CounterfactualHost, HostAdapter
from faultlattice.model import ModelProvider
from faultlattice.runner import execute_run, load_manifest
from faultlattice.schemas import ExecutionMode, TaskDefinition
from faultlattice.trace import read_jsonl


class CounterfactualRunner:
    """执行 M3 反事实续跑并生成独立四件套。"""

    def __init__(
        self,
        host: HostAdapter,
        model: ModelProvider,
        *,
        runs_root: Path,
        repo_root: Path,
    ) -> None:
        self.host = host
        self.model = model
        self.runs_root = Path(runs_root)
        self.repo_root = Path(repo_root)

    @staticmethod
    def _prefix_before_first_injection(source_run_dir: Path) -> list[dict[str, Any]]:
        """提取目标 tool_call 契约；预设内容只用于匹配，不进入真实模型上下文。"""
        prefix: list[dict[str, Any]] = []
        for step in read_jsonl(Path(source_run_dir) / "steps.jsonl"):
            event_type = step.get("event_type")
            if event_type == "injection":
                break
            if event_type == "tool_call":
                prefix.append(
                    {
                        "tool_call": {
                            "name": step["tool_name"],
                            "args": step.get("arguments", {}),
                        }
                    }
                )
            elif event_type == "model_output":
                prefix.append({"final_answer": step.get("content", "")})
        if not prefix or "tool_call" not in prefix[-1]:
            raise ReplayError("M3 源轨迹必须在首次注入前包含目标 tool_call")
        return prefix

    def run(self, task: TaskDefinition) -> Path:
        """校验源契约，由真实模型建立前缀并执行故障后的续跑。"""
        if task.mode is not ExecutionMode.M3 or task.counterfactual_source is None:
            raise ReplayError("CounterfactualRunner 只接受带 counterfactual_source 的 M3 任务")
        if not isinstance(self.host, CounterfactualHost):
            raise ReplayError(f"宿主 {task.host} 不支持 M3 反事实续跑")
        source_dir = Path(task.counterfactual_source)
        if not source_dir.is_absolute():
            source_dir = self.repo_root / source_dir
        source = load_manifest(source_dir)
        if source.task.host != task.host:
            raise ReplayError("M3 任务与源 run 的宿主不一致")
        if source.task.fault != task.fault:
            raise ReplayError("M3 任务与源 run 的故障声明不一致")
        if not source.injection_applied:
            raise ReplayError("源 run 的故障未实际生效，不能作为 M3 起点")
        task_protocol = task.model.state_claim_protocol if task.model is not None else None
        provider_protocol = getattr(self.model, "state_claim_protocol", None)
        if provider_protocol != task_protocol:
            raise ConfigurationError(
                "模型提供方状态声明协议与任务冻结值不一致: "
                f"provider={provider_protocol or 'missing'}, task={task_protocol or 'missing'}"
            )
        prefix = self._prefix_before_first_injection(source_dir)
        return execute_run(
            task,
            self.host,
            runs_root=self.runs_root,
            repo_root=self.repo_root,
            script_override=prefix,
            model_provider=self.model,
        )
