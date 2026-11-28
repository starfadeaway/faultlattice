"""本地受控测试宿主（M0–M2 用）。

这是一个最小、确定性的工具调用程序，用于 golden cases 与 CLI 纵向切片。
它不是被测真实 Agent（真实宿主如 smolagents 以后以独立 adapter 接入），
只是一个行为完全可预测的"框架"：

- 按脚本顺序执行 tool_call；
- write_file 在沙箱内写入文件（真实副作用）；
- 参数校验失败抛 TypeError（invalid_args 的实际表现由此产生，
  adapter 如实记录，而不是只记录预期）；
- 工具异常 / 带 error 键的返回值 → 框架向调用方报告 failed；
- 否则报告 completed 并输出脚本中的 final_answer。

注入语义：
- tool_args 注入：在工具校验前改写参数；
- tool_result 注入：工具真实执行（副作用发生），但返回给框架的
  结果 / 异常被 FaultSpec 替换；
- observation 注入：本地宿主没有独立 observation 通道（preset 脚本即
  上下文），本 adapter 不支持 observation 注入，预检时显式报错，
  防止假绿。
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from faultlattice.errors import AdapterCapabilityError, ConfigurationError
from faultlattice.faults import build_fault_effect
from faultlattice.host import HostRunResult
from faultlattice.process_timeout import ProcessTimeoutError, run_with_process_timeout
from faultlattice.schemas import FaultSpec, FaultType, InjectionPoint, SurfaceAs


def _write_file_tool(
    args: dict[str, Any], sandbox: Path, *, delay_seconds: float = 0.0
) -> dict[str, Any]:
    """顶层工具入口必须可由 spawn 序列化；延迟发生在真实写入之前。"""
    sandbox = Path(sandbox).resolve()
    path = args.get("path")
    content = args.get("content")
    if not isinstance(path, str) or not isinstance(content, str):
        raise TypeError(
            f"write_file 参数类型错误: path={type(path).__name__}, "
            f"content={type(content).__name__}"
        )
    if delay_seconds:
        time.sleep(delay_seconds)
    target = (sandbox / path).resolve()
    if target != sandbox and sandbox not in target.parents:
        raise ConfigurationError(f"write_file 路径越出沙箱: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return {"written": Path(path).as_posix(), "bytes": len(content.encode("utf-8"))}


class LocalControlledHost:
    """确定性本地宿主。实现 faultlattice.host.HostAdapter 协议。"""

    name = "local_controlled"
    # in-tree 测试宿主，无独立包版本；versions.py 会在 null_reasons 说明
    package_version: str | None = None
    host_commit: str | None = None

    def preflight(self, fault: FaultSpec | None) -> None:
        """注入点与进程参数预检：不支持或无法判定的配置显式报错。"""
        if fault is not None and fault.injection_point is InjectionPoint.OBSERVATION:
            raise AdapterCapabilityError(
                f"宿主 {self.name} 没有独立的 observation 通道，"
                "不支持 observation 注入；不能静默跳过或假装注入成功。"
            )
        if fault is None:
            return
        mode = fault.params.get("timeout_mode", "simulated")
        if mode not in ("simulated", "process"):
            raise ConfigurationError("timeout_mode 只能是 simulated 或 process")
        if mode == "process" and (
            fault.injection_point is not InjectionPoint.TOOL_RESULT
            or fault.fault_type is not FaultType.TIMEOUT
        ):
            raise AdapterCapabilityError("进程硬终止只支持 tool_result / timeout")
        if mode != "process":
            return
        timeout = fault.params.get("timeout_seconds")
        delay = fault.params.get("tool_delay_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ConfigurationError("进程超时需要数值型 timeout_seconds")
        if isinstance(delay, bool) or not isinstance(delay, (int, float)):
            raise ConfigurationError("进程超时需要数值型 tool_delay_seconds")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ConfigurationError("timeout_seconds 必须是有限正数")
        if not math.isfinite(delay) or delay < 0:
            raise ConfigurationError("tool_delay_seconds 必须是有限非负数")

    # ------------------------------------------------------------------ run

    def run_script(
        self,
        script: list[dict[str, Any]],
        *,
        fault: FaultSpec | None = None,
        sandbox: Path,
    ) -> HostRunResult:
        # 在预检前重置，早期失败也不能误带上一次运行的事件。
        events: list[dict[str, Any]] = []
        self.last_events = events
        sandbox = Path(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
        self.preflight(fault)

        final_answer: str | None = None
        framework_outcome = "completed"

        for item in script:
            if "tool_call" in item:
                call = item["tool_call"]
                tool_name = call["name"]
                args = dict(call.get("args", {}))
                events.append(
                    {"kind": "tool_call", "tool_name": tool_name, "arguments": dict(args)}
                )

                injected_exception: BaseException | None = None
                injected_return: Any = None
                has_injected_return = False
                result: Any = None
                injected = False

                if fault is not None and fault.injection_point is InjectionPoint.TOOL_ARGS:
                    # 改写参数：默认把 path 换成非字符串，触发宿主校验抛错
                    corrupted = dict(args)
                    corrupted.update(fault.params.get("corrupt_args", {"path": 123}))
                    effect = build_fault_effect(
                        fault.fault_type, fault.surface_as, fault.params, original=args
                    )
                    applied = corrupted != args
                    events.append(
                        {
                            "kind": "injection",
                            "injection_point": fault.injection_point.value,
                            "fault_type": fault.fault_type.value,
                            "surface_as": fault.surface_as.value,
                            "original": args,
                            "replacement": corrupted,
                            "raised": None,
                            "applied": applied,
                        }
                    )
                    injected = applied
                    args = corrupted
                    if fault.surface_as is SurfaceAs.RAISE_EXCEPTION and applied:
                        injected_exception = effect.exception
                    elif fault.surface_as is SurfaceAs.RETURN_VALUE and applied:
                        # return_value 必须在普通返回通道呈现，不得再把坏参数交给
                        # 真实工具并让它抛 TypeError；工具未执行，因此没有副作用。
                        injected_return = effect.replacement
                        has_injected_return = True

                process_requested = bool(
                    fault is not None and fault.params.get("timeout_mode") == "process"
                )
                process_timed_out = False
                try:
                    if injected_exception is not None:
                        raise injected_exception
                    if has_injected_return:
                        result = injected_return
                    elif process_requested:
                        assert fault is not None
                        try:
                            result = run_with_process_timeout(
                                _write_file_tool,
                                args,
                                sandbox,
                                delay_seconds=float(fault.params["tool_delay_seconds"]),
                                timeout_seconds=float(fault.params["timeout_seconds"]),
                            )
                        except ProcessTimeoutError as exc:
                            process_timed_out = True
                            injected = True
                            text = str(fault.params.get("message") or str(exc))
                            replacement = (
                                None
                                if fault.surface_as is SurfaceAs.RAISE_EXCEPTION
                                else {"error": "timeout", "message": text}
                            )
                            events.append(
                                {
                                    "kind": "injection",
                                    "injection_point": fault.injection_point.value,
                                    "fault_type": fault.fault_type.value,
                                    "surface_as": fault.surface_as.value,
                                    "original": None,
                                    "replacement": replacement,
                                    "raised": (
                                        "TimeoutError" if replacement is None else None
                                    ),
                                    "applied": True,
                                    "timeout_mode": "process",
                                    "timeout_seconds": float(fault.params["timeout_seconds"]),
                                    "tool_delay_seconds": float(
                                        fault.params["tool_delay_seconds"]
                                    ),
                                    "worker_pid": exc.worker_pid,
                                    "elapsed_seconds": exc.elapsed_seconds,
                                    "process_terminated": exc.process_terminated,
                                }
                            )
                            if replacement is None:
                                # 对宿主保持 TimeoutError 信号；子进程确实已经终止。
                                raise TimeoutError(text) from exc
                            result = replacement
                    else:
                        result = _write_file_tool(args, sandbox)

                    if (
                        fault is not None
                        and fault.injection_point is InjectionPoint.TOOL_RESULT
                        and not process_requested
                    ):
                        effect = build_fault_effect(
                            fault.fault_type, fault.surface_as, fault.params, original=result
                        )
                        if effect.raises:
                            events.append(
                                {
                                    "kind": "injection",
                                    "injection_point": fault.injection_point.value,
                                    "fault_type": fault.fault_type.value,
                                    "surface_as": fault.surface_as.value,
                                    "original": result,
                                    "replacement": None,
                                    "raised": type(effect.exception).__name__,
                                    "applied": True,
                                }
                            )
                            injected = True
                            raise effect.exception  # type: ignore[misc]
                        applied = effect.replacement != result
                        events.append(
                            {
                                "kind": "injection",
                                "injection_point": fault.injection_point.value,
                                "fault_type": fault.fault_type.value,
                                "surface_as": fault.surface_as.value,
                                "original": result,
                                "replacement": effect.replacement,
                                "raised": None,
                                "applied": applied,
                            }
                        )
                        injected = applied
                        result = effect.replacement
                    elif process_requested and not process_timed_out:
                        assert fault is not None
                        # 子进程正常完成就没有发生真实超时，绝不能补一个模拟异常充数。
                        events.append(
                            {
                                "kind": "injection",
                                "injection_point": fault.injection_point.value,
                                "fault_type": fault.fault_type.value,
                                "surface_as": fault.surface_as.value,
                                "original": result,
                                "replacement": result,
                                "raised": None,
                                "applied": False,
                                "timeout_mode": "process",
                                "reason": "timeout_not_reached",
                            }
                        )

                    events.append(
                        {
                            "kind": "tool_result",
                            "tool_name": tool_name,
                            "result": result,
                            "error": None,
                            "injected": injected,
                        }
                    )
                    # 框架策略：返回值带 error 键视为失败信号
                    if isinstance(result, dict) and "error" in result:
                        framework_outcome = "failed"
                        break
                except (TypeError, TimeoutError, RuntimeError) as exc:
                    events.append(
                        {
                            "kind": "tool_result",
                            "tool_name": tool_name,
                            "result": None,
                            "error": type(exc).__name__,
                            "injected": injected,
                        }
                    )
                    framework_outcome = "failed"
                    break
            elif "final_answer" in item:
                final_answer = item["final_answer"]
                events.append({"kind": "model_output", "content": final_answer, "preset": True})
            else:
                raise ConfigurationError(f"脚本项无法识别（需要 tool_call 或 final_answer）: {item}")

        return HostRunResult(
            framework_outcome=framework_outcome,
            final_answer=final_answer if framework_outcome == "completed" else None,
            events=events,
        )
