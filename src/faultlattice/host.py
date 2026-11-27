"""宿主 adapter 协议（core 侧定义，不依赖任何具体宿主）。

依赖方向（spec 第 8 节）：core 只定义协议，adapters 实现协议并依赖 core；
runner / replay 只面向本模块的 Protocol 编程，由 CLI 负责装配具体宿主。
这样 AST 依赖检查可以保证 core 不会反向 import adapters。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class HostRunResult:
    """一次宿主执行的结果：框架返回给调用方的信号与最终回答。

    framework_outcome 是"框架向调用方报告的结果"（completed / failed），
    与任务是否真的成功无关——两者的错位正是 Oracle 要检测的对象。
    """

    def __init__(
        self,
        *,
        framework_outcome: str,
        final_answer: str | None,
        events: list[dict[str, Any]],
        model_invoked: bool = False,
        observation_status: str = "not_applicable",
        model_id: str | None = None,
        sampling_params: dict[str, Any] | None = None,
    ) -> None:
        if framework_outcome not in ("completed", "failed"):
            raise ValueError(f"非法 framework_outcome: {framework_outcome}")
        self.framework_outcome = framework_outcome
        self.final_answer = final_answer
        # 结构化事件（tool_call / tool_result / injection 等），由 runner 加上
        # 公共字段后写入 steps.jsonl
        self.events = events
        self.model_invoked = model_invoked
        self.observation_status = observation_status
        self.model_id = model_id
        self.sampling_params = sampling_params


class PostconditionObservation:
    """宿主在运行结束后对真实业务状态的只读观察。

    适配器必须查询实际状态，不得复述工具返回或最终回答。证据不足时显式设置
    evidence_sufficient=False，由 runner 交给 Oracle 判为 inconclusive。
    """

    def __init__(
        self,
        *,
        task_succeeded: bool,
        side_effects_as_expected: bool,
        evidence: dict[str, Any],
        evidence_sufficient: bool = True,
    ) -> None:
        self.task_succeeded = task_succeeded
        self.side_effects_as_expected = side_effects_as_expected
        self.evidence = evidence
        self.evidence_sufficient = evidence_sufficient


@runtime_checkable
class StatefulHost(Protocol):
    """支持 host_state 后置条件的宿主；观察必须与执行路径分开。"""

    def observe_postcondition(
        self, expected: Any, *, sandbox: Path
    ) -> PostconditionObservation:
        """以只读方式核验预注册业务状态，并返回可序列化的安全证据。"""
        ...


@runtime_checkable
class HostAdapter(Protocol):
    """被测宿主必须实现的协议。

    防假绿约束（spec/开发提示词）：实现方必须保证 injected 故障确实改变了
    目标内容，并通过事件中的 injection 记录暴露注入前后内容；只有调用
    记录而内容未变时，runner 会把 injection_applied 记为 False。
    """

    name: str
    package_version: str | None  # 宿主包版本；in-tree 宿主为 None 并说明原因
    host_commit: str | None  # 外部宿主源码 commit；无法获得时为 None 并说明原因

    def run_script(
        self,
        script: list[dict[str, Any]],
        *,
        fault: Any | None = None,
        sandbox: Path,
    ) -> HostRunResult:
        """执行一段（预设或重建的）模型输出脚本，返回结构化结果。"""
        ...


@runtime_checkable
class CounterfactualHost(Protocol):
    """支持 M3 的宿主协议；续跑循环仍由宿主实现，核心不接管 Agent loop。"""

    def run_counterfactual(
        self,
        script: list[dict[str, Any]],
        *,
        fault: Any,
        sandbox: Path,
        model_provider: Any,
    ) -> HostRunResult:
        """由真实模型建立匹配脚本契约的前缀，再从注入后的观察续跑。"""
        ...
