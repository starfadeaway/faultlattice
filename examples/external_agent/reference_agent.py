"""可由控制台登记的外部 HostAdapter 参考实现。

它故意放在 FaultLattice 内置 adapters 包之外，用来验证“从用户指定的 Python
文件加载第三方宿主”这一真实路径。该类是确定性的 M0 参考 Agent，不调用模型；
生产 Agent 应在同一协议中接入自己的循环、工具和注入边界。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from faultlattice.errors import AdapterCapabilityError, ConfigurationError
from faultlattice.faults import build_fault_effect
from faultlattice.host import HostRunResult
from faultlattice.schemas import FaultSpec, InjectionPoint, SurfaceAs


class ReferenceAgent:
    name = "reference_external_agent"
    package_version = "1.0.0"
    host_commit = None
    capabilities = {
        "modes": ["M0"],
        "injection_points": ["tool_args", "tool_result"],
        "tools": ["write_file"],
    }

    def preflight(self, fault: FaultSpec | None) -> None:
        if fault is not None and fault.injection_point not in (
            InjectionPoint.TOOL_ARGS,
            InjectionPoint.TOOL_RESULT,
        ):
            raise AdapterCapabilityError("ReferenceAgent 只支持 tool_args / tool_result")

    @staticmethod
    def _write_file(args: dict[str, Any], sandbox: Path) -> dict[str, Any]:
        path = args.get("path")
        content = args.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise TypeError("ReferenceAgent write_file 要求 path 与 content 都是字符串")
        target = (sandbox / path).resolve()
        if target == sandbox or sandbox not in target.parents:
            raise ConfigurationError("ReferenceAgent 拒绝沙箱外或沙箱根路径写入")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        return {"written": path, "bytes": len(content.encode("utf-8"))}

    @staticmethod
    def _injection(
        fault: FaultSpec,
        *,
        original: Any,
        replacement: Any,
        raised: str | None,
        applied: bool,
    ) -> dict[str, Any]:
        return {
            "kind": "injection",
            "injection_point": fault.injection_point.value,
            "fault_type": fault.fault_type.value,
            "surface_as": fault.surface_as.value,
            "original": original,
            "replacement": replacement,
            "raised": raised,
            "applied": applied,
        }

    def run_script(
        self,
        script: list[dict[str, Any]],
        *,
        fault: FaultSpec | None = None,
        sandbox: Path,
    ) -> HostRunResult:
        sandbox = Path(sandbox).resolve()
        sandbox.mkdir(parents=True, exist_ok=True)
        self.preflight(fault)
        events: list[dict[str, Any]] = []
        final_answer: str | None = None
        outcome = "completed"

        for item in script:
            if "tool_call" in item:
                call = item["tool_call"]
                if call.get("name") != "write_file":
                    raise AdapterCapabilityError("ReferenceAgent 只登记了 write_file 工具")
                arguments = dict(call.get("args", {}))
                original_arguments = dict(arguments)
                events.append(
                    {"kind": "tool_call", "tool_name": "write_file", "arguments": arguments}
                )
                injected = False
                pending_exception: BaseException | None = None
                invalid_args_effect = None

                if fault is not None and fault.injection_point is InjectionPoint.TOOL_ARGS:
                    arguments.update(fault.params.get("corrupt_args", {"path": 123}))
                    applied = arguments != original_arguments
                    invalid_args_effect = build_fault_effect(
                        fault.fault_type, fault.surface_as, fault.params, original=original_arguments
                    )
                    pending_exception = (
                        invalid_args_effect.exception
                        if fault.surface_as is SurfaceAs.RAISE_EXCEPTION and applied
                        else None
                    )
                    events.append(
                        self._injection(
                            fault,
                            original=original_arguments,
                            replacement=arguments,
                            raised=(
                                type(pending_exception).__name__ if pending_exception else None
                            ),
                            applied=applied,
                        )
                    )
                    injected = applied

                try:
                    if pending_exception is not None:
                        raise pending_exception
                    result = self._write_file(arguments, sandbox)
                except TypeError as exc:
                    if invalid_args_effect is not None and not invalid_args_effect.raises:
                        result = invalid_args_effect.replacement
                    else:
                        events.append(
                            {
                                "kind": "tool_result",
                                "tool_name": "write_file",
                                "result": None,
                                "error": type(exc).__name__,
                                "injected": injected,
                            }
                        )
                        outcome = "failed"
                        break

                if fault is not None and fault.injection_point is InjectionPoint.TOOL_RESULT:
                    effect = build_fault_effect(
                        fault.fault_type, fault.surface_as, fault.params, original=result
                    )
                    if effect.raises:
                        events.append(
                            self._injection(
                                fault,
                                original=result,
                                replacement=None,
                                raised=type(effect.exception).__name__,
                                applied=True,
                            )
                        )
                        events.append(
                            {
                                "kind": "tool_result",
                                "tool_name": "write_file",
                                "result": None,
                                "error": type(effect.exception).__name__,
                                "injected": True,
                            }
                        )
                        outcome = "failed"
                        break
                    applied = effect.replacement != result
                    events.append(
                        self._injection(
                            fault,
                            original=result,
                            replacement=effect.replacement,
                            raised=None,
                            applied=applied,
                        )
                    )
                    result = effect.replacement
                    injected = applied

                events.append(
                    {
                        "kind": "tool_result",
                        "tool_name": "write_file",
                        "result": result,
                        "error": None,
                        "injected": injected,
                    }
                )
                if isinstance(result, dict) and "error" in result:
                    outcome = "failed"
                    break
            elif "final_answer" in item:
                answer = item["final_answer"]
                if not isinstance(answer, str):
                    raise ConfigurationError("ReferenceAgent final_answer 必须是字符串")
                final_answer = answer
                events.append({"kind": "model_output", "content": answer, "preset": True})
            else:
                raise ConfigurationError("ReferenceAgent 无法识别脚本项")

        return HostRunResult(
            framework_outcome=outcome,
            final_answer=final_answer if outcome == "completed" else None,
            events=events,
        )


class ToolArgsReferenceAgent(ReferenceAgent):
    """只开放参数注入边界，用于验证宿主能力声明与任务筛选。"""

    name = "reference_tool_args_agent"
    capabilities = {
        "modes": ["M0"],
        "injection_points": ["tool_args"],
        "tools": ["write_file"],
    }

    def preflight(self, fault: FaultSpec | None) -> None:
        if fault is not None and fault.injection_point is not InjectionPoint.TOOL_ARGS:
            raise AdapterCapabilityError("ToolArgsReferenceAgent 只支持 tool_args")


class ToolResultReferenceAgent(ReferenceAgent):
    """只开放工具结果注入边界，保留真实写入与结果替换流程。"""

    name = "reference_tool_result_agent"
    capabilities = {
        "modes": ["M0"],
        "injection_points": ["tool_result"],
        "tools": ["write_file"],
    }

    def preflight(self, fault: FaultSpec | None) -> None:
        if fault is not None and fault.injection_point is not InjectionPoint.TOOL_RESULT:
            raise AdapterCapabilityError("ToolResultReferenceAgent 只支持 tool_result")
