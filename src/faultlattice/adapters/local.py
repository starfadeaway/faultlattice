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

from pathlib import Path
from typing import Any

from faultlattice.errors import AdapterCapabilityError, ConfigurationError
from faultlattice.faults import build_fault_effect
from faultlattice.host import HostRunResult
from faultlattice.schemas import FaultSpec, InjectionPoint, SurfaceAs


class LocalControlledHost:
    """确定性本地宿主。实现 faultlattice.host.HostAdapter 协议。"""

    name = "local_controlled"
    # in-tree 测试宿主，无独立包版本；versions.py 会在 null_reasons 说明
    package_version: str | None = None

    def preflight(self, fault: FaultSpec | None) -> None:
        """注入点预检：不支持的注入显式报错（防假绿）。"""
        if fault is not None and fault.injection_point is InjectionPoint.OBSERVATION:
            raise AdapterCapabilityError(
                f"宿主 {self.name} 没有独立的 observation 通道，"
                "不支持 observation 注入；不能静默跳过或假装注入成功。"
            )

    # ------------------------------------------------------------------ tools

    def _write_file(self, args: dict[str, Any], sandbox: Path) -> dict[str, Any]:
        path = args.get("path")
        content = args.get("content")
        # 参数校验：invalid_args 注入的实际表现就是这里抛出的 TypeError
        if not isinstance(path, str) or not isinstance(content, str):
            raise TypeError(
                f"write_file 参数类型错误: path={type(path).__name__}, "
                f"content={type(content).__name__}"
            )
        target = (sandbox / path).resolve()
        if not str(target).startswith(str(sandbox.resolve())):
            raise ConfigurationError(f"write_file 路径越出沙箱: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        return {"written": str(Path(path)), "bytes": len(content.encode("utf-8"))}

    # ------------------------------------------------------------------ run

    def run_script(
        self,
        script: list[dict[str, Any]],
        *,
        fault: FaultSpec | None = None,
        sandbox: Path,
    ) -> HostRunResult:
        sandbox = Path(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
        self.preflight(fault)

        events: list[dict[str, Any]] = []
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
                        # raise_exception 形态：校验错误以异常呈现；本地宿主的
                        # 校验本身就会抛 TypeError，这里显式使用注入构造的异常
                        injected_exception = effect.exception

                try:
                    if injected_exception is not None:
                        raise injected_exception
                    result = self._write_file(args, sandbox)

                    if (
                        fault is not None
                        and fault.injection_point is InjectionPoint.TOOL_RESULT
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
