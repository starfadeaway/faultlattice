"""故障模型：合法组合校验、experiment_family 推导、故障效果构造。

合法组合表见 docs/spec-v0.1.md 第 3 节与 docs/NAMING.md 第 3 节。
未列出的组合直接报 ConfigurationError，不静默跳过。

注意（spec 第 3 节末）：第一版同步工具超时只做确定性模拟 TimeoutError；
不得声称 asyncio.to_thread + wait_for 能真正终止同步函数，真实硬终止
需要进程隔离，后续实现。因此本模块构造的 timeout 效果是"立即抛出
TimeoutError"，语义上等价于"宿主在超时点收到 TimeoutError"，
不代表真实时钟等待。
"""

from __future__ import annotations

from typing import Any

from faultlattice.errors import ConfigurationError
from faultlattice.schemas import (
    ExperimentFamily,
    FaultType,
    InjectionPoint,
    SurfaceAs,
)

# spec 第 3 节表格的机读形式：唯一事实来源，FaultSpec 校验与测试都引用它。
LEGAL_COMBINATIONS: frozenset[tuple[InjectionPoint, FaultType, SurfaceAs]] = frozenset(
    {
        (InjectionPoint.TOOL_ARGS, FaultType.INVALID_ARGS, SurfaceAs.RAISE_EXCEPTION),
        (InjectionPoint.TOOL_ARGS, FaultType.INVALID_ARGS, SurfaceAs.RETURN_VALUE),
        (InjectionPoint.TOOL_RESULT, FaultType.TIMEOUT, SurfaceAs.RAISE_EXCEPTION),
        (InjectionPoint.TOOL_RESULT, FaultType.TIMEOUT, SurfaceAs.RETURN_VALUE),
        (InjectionPoint.TOOL_RESULT, FaultType.EMPTY_RESPONSE, SurfaceAs.RETURN_VALUE),
        (InjectionPoint.TOOL_RESULT, FaultType.ERROR_RESPONSE, SurfaceAs.RETURN_VALUE),
        (InjectionPoint.TOOL_RESULT, FaultType.ERROR_RESPONSE, SurfaceAs.RAISE_EXCEPTION),
        (InjectionPoint.TOOL_RESULT, FaultType.TRUNCATED, SurfaceAs.RETURN_VALUE),
        (InjectionPoint.TOOL_RESULT, FaultType.MALFORMED_CONTENT, SurfaceAs.RETURN_VALUE),
        (InjectionPoint.OBSERVATION, FaultType.EMPTY_RESPONSE, SurfaceAs.NOT_APPLICABLE),
        (InjectionPoint.OBSERVATION, FaultType.TRUNCATED, SurfaceAs.NOT_APPLICABLE),
        (InjectionPoint.OBSERVATION, FaultType.MALFORMED_CONTENT, SurfaceAs.NOT_APPLICABLE),
        (InjectionPoint.OBSERVATION, FaultType.ERROR_RESPONSE, SurfaceAs.NOT_APPLICABLE),
    }
)


def derive_experiment_family(injection_point: InjectionPoint) -> ExperimentFamily:
    """experiment_family 只能由 injection_point 推导，不允许调用方填写。"""
    if injection_point is InjectionPoint.OBSERVATION:
        return ExperimentFamily.CONTEXT_CORRUPTION
    return ExperimentFamily.TOOL_FAULT


def check_legal_combination(
    injection_point: InjectionPoint, fault_type: FaultType, surface_as: SurfaceAs
) -> None:
    """校验故障组合合法性；非法组合报 ConfigurationError。"""
    if (injection_point, fault_type, surface_as) not in LEGAL_COMBINATIONS:
        raise ConfigurationError(
            "非法故障组合: "
            f"injection_point={injection_point}, fault_type={fault_type}, surface_as={surface_as}。"
            "合法组合见 docs/spec-v0.1.md 第 3 节；不支持的组合必须显式报错，不能静默跳过。"
        )


class InjectedFaultEffect:
    """一次注入对工具返回 / observation 的实际效果。

    - surface_as = raise_exception：``exception`` 非空，宿主应让它按异常传播；
    - surface_as = return_value：``replacement`` 是替换后的返回值；
    - observation 注入：``replacement`` 是替换后的 observation 文本，
      exception 恒为 None（observation 没有 return / raise 语义）。
    """

    def __init__(self, replacement: Any = None, exception: BaseException | None = None) -> None:
        self.replacement = replacement
        self.exception = exception

    @property
    def raises(self) -> bool:
        return self.exception is not None


def build_fault_effect(
    fault_type: FaultType,
    surface_as: SurfaceAs,
    params: dict[str, Any],
    original: Any,
) -> InjectedFaultEffect:
    """按 FaultSpec 构造注入效果。

    ``original`` 是被替换前的工具返回 / observation，truncated 等故障
    需要基于它构造。返回的效果是否真正生效，由 adapter 对比注入前后的
    实际内容来确认（injection_applied），本函数只负责"应该改成什么"。
    """
    message = str(params.get("message", ""))

    if fault_type is FaultType.TIMEOUT:
        # 确定性模拟：不等待真实时钟，直接产生超时效果（见模块 docstring）
        text = message or "tool call timed out (simulated)"
        if surface_as is SurfaceAs.RAISE_EXCEPTION:
            return InjectedFaultEffect(exception=TimeoutError(text))
        return InjectedFaultEffect(replacement={"error": "timeout", "message": text})

    if fault_type is FaultType.EMPTY_RESPONSE:
        # 空响应具体形态由 params.empty 指定，默认空对象
        replacement = params.get("empty", {})
        return InjectedFaultEffect(replacement=replacement)

    if fault_type is FaultType.ERROR_RESPONSE:
        text = message or "tool execution failed (simulated)"
        if surface_as is SurfaceAs.RAISE_EXCEPTION:
            return InjectedFaultEffect(exception=RuntimeError(text))
        return InjectedFaultEffect(replacement={"error": "error_response", "message": text})

    if fault_type is FaultType.TRUNCATED:
        original_text = original if isinstance(original, str) else str(original)
        # keep 是保留的字符数；默认保留一半，至少暴露"被截断"这一事实
        keep = int(params.get("keep", max(1, len(original_text) // 2)))
        return InjectedFaultEffect(replacement=original_text[:keep])

    if fault_type is FaultType.MALFORMED_CONTENT:
        # 结构或格式错误：默认返回一段不是合法 JSON 的残片
        replacement = params.get("malformed", '{"broken": ')
        return InjectedFaultEffect(replacement=replacement)

    if fault_type is FaultType.INVALID_ARGS:
        # invalid_args 的表现取决于宿主校验方式；adapter 必须记录实际表现。
        # 这里只提供 Harness 侧的默认错误描述。
        text = message or "invalid tool arguments (simulated)"
        if surface_as is SurfaceAs.RAISE_EXCEPTION:
            return InjectedFaultEffect(exception=TypeError(text))
        return InjectedFaultEffect(replacement={"error": "invalid_args", "message": text})

    # FaultType 是枚举且上面全覆盖；走到这里说明枚举被扩展而本函数未跟上
    raise ConfigurationError(f"未处理的 fault_type: {fault_type}")
