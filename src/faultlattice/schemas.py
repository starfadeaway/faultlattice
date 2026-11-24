"""Pydantic 数据模型：故障规范、任务预注册、轨迹事件、Oracle 判定、运行清单。

所有枚举取值与 docs/NAMING.md 一一对应，改名必须先改 NAMING.md。

序列化约定（spec 第 7.1 节）：写盘前统一 ``model_dump(mode="json")``，
再交给 faultlattice.canonical 编码；datetime 一律带时区。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from faultlattice.errors import ConfigurationError

# ---------------------------------------------------------------------------
# 枚举：取值即 NAMING.md 中的登记名
# ---------------------------------------------------------------------------


class InjectionPoint(StrEnum):
    TOOL_ARGS = "tool_args"
    TOOL_RESULT = "tool_result"
    OBSERVATION = "observation"


class FaultType(StrEnum):
    TIMEOUT = "timeout"
    EMPTY_RESPONSE = "empty_response"
    TRUNCATED = "truncated"
    MALFORMED_CONTENT = "malformed_content"
    ERROR_RESPONSE = "error_response"
    INVALID_ARGS = "invalid_args"


class SurfaceAs(StrEnum):
    RETURN_VALUE = "return_value"
    RAISE_EXCEPTION = "raise_exception"
    NOT_APPLICABLE = "not_applicable"


class ExperimentFamily(StrEnum):
    TOOL_FAULT = "tool_fault"
    CONTEXT_CORRUPTION = "context_corruption"


class ExecutionMode(StrEnum):
    M0 = "M0"  # 预设脚本
    M1 = "M1"  # 纯轨迹重放
    M2 = "M2"  # 故障注入重放
    M3 = "M3"  # 反事实续跑


class TargetLayer(StrEnum):
    FRAMEWORK = "framework"
    MODEL = "model"


class FrameworkVerdict(StrEnum):
    COMPLETED = "completed"
    EXPLICIT_FAILURE = "explicit_failure"
    SILENT_FAILURE = "silent_failure"
    CONTRACT_VIOLATION = "contract_violation"
    INCONCLUSIVE = "inconclusive"


class ModelVerdict(StrEnum):
    COMPLETED = "completed"
    EXPLICIT_FAILURE = "explicit_failure"
    SILENT_FAILURE = "silent_failure"
    CONTRACT_VIOLATION = "contract_violation"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class NotApplicableReason(StrEnum):
    LAYER_NOT_TARGETED = "layer_not_targeted"
    INJECTION_FAILED = "injection_failed"
    MODE_NOT_APPLICABLE = "mode_not_applicable"
    MODEL_NOT_INVOKED = "model_not_invoked"


class InconclusiveReason(StrEnum):
    INJECTION_FAILED = "injection_failed"
    ORACLE_EVIDENCE_INSUFFICIENT = "oracle_evidence_insufficient"


class ObservationStatus(StrEnum):
    REACHED = "reached"
    NOT_REACHED = "not_reached"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class OracleSource(StrEnum):
    STATE = "state"
    RULE = "rule"
    HUMAN = "human"
    JUDGE = "judge"


class OracleDeterminism(StrEnum):
    DETERMINISTIC = "deterministic"
    STOCHASTIC = "stochastic"


class OracleValidation(StrEnum):
    UNVALIDATED = "unvalidated"
    GOLDEN_VERIFIED = "golden_verified"
    HUMAN_ALIGNED = "human_aligned"


# ---------------------------------------------------------------------------
# 故障规范
# ---------------------------------------------------------------------------


class FaultSpec(BaseModel):
    """一次故障注入的完整描述。

    experiment_family 不是字段，而是由 injection_point 推导的属性
    （见 faultlattice.faults.derive_experiment_family），调用方无法填写。
    """

    model_config = ConfigDict(frozen=True)

    injection_point: InjectionPoint
    fault_type: FaultType
    surface_as: SurfaceAs
    # 故障参数：如 message（错误文本）、keep（截断保留字符数）、
    # empty（空响应的具体形态）、malformed（畸形内容样本）
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_legal(self) -> FaultSpec:
        # 延迟 import 避免循环：faults 依赖 schemas 的枚举
        from faultlattice.faults import check_legal_combination

        check_legal_combination(self.injection_point, self.fault_type, self.surface_as)
        return self

    @property
    def experiment_family(self) -> ExperimentFamily:
        from faultlattice.faults import derive_experiment_family

        return derive_experiment_family(self.injection_point)


# ---------------------------------------------------------------------------
# 任务预注册（spec 第 4.1 节）
# ---------------------------------------------------------------------------


class OracleSpec(BaseModel):
    """Oracle 元数据。deterministic 不等于天然正确，见 spec 第 5.3 节。"""

    model_config = ConfigDict(frozen=True)

    source: OracleSource
    determinism: OracleDeterminism
    validation: OracleValidation
    description: str = ""


class ExpectedPostcondition(BaseModel):
    """机器可检查的预期后置条件。

    kind 的取值由 Oracle 判定器解释；第一版支持：
    - file_written：params = {"path": 相对沙箱路径, "content_contains": 可选子串}
    """

    model_config = ConfigDict(frozen=True)

    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class TaskDefinition(BaseModel):
    """任务 × 宿主的预注册声明。

    这里的字段必须在看到实验结果前写入任务定义文件；运行时原样复制进
    run.json，禁止事后倒填（spec 第 4.1 节）。
    """

    task_id: str
    description: str = ""
    host: str
    mode: ExecutionMode
    # 故障规范；M1 纯轨迹重放不注入故障，允许为 None
    fault: FaultSpec | None = None
    target_layers: list[TargetLayer] = Field(min_length=1)
    expected_postcondition: ExpectedPostcondition
    expected_behavior: str
    fault_recoverable: bool
    allowed_degradation: list[str] = Field(default_factory=list)
    oracle: OracleSpec
    inconclusive_threshold: float = Field(ge=0.0, le=1.0)
    inconclusive_reporting: str = ""
    min_evaluable: int = Field(ge=1)
    pair_id: str | None = None
    # M0 预设脚本：模型输出的手写序列（仅 M0 使用）。
    # 元素形如 {"tool_call": {...}} 或 {"final_answer": "..."}。
    script: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_layers_match_mode(self) -> TaskDefinition:
        # spec 第 4.1 节：M0–M2 本地框架实验用 [framework]；
        # 只有评价真实模型反应的 M3 才加入 model，不能不看模式一律声明两层。
        if self.mode in (ExecutionMode.M0, ExecutionMode.M1, ExecutionMode.M2) and (
            TargetLayer.MODEL in self.target_layers
        ):
            raise ConfigurationError(
                f"任务 {self.task_id}: 执行模式 {self.mode} 不产生真实模型反应，"
                "target_layers 不得包含 model（spec 第 4.1 节）。"
            )
        return self


# ---------------------------------------------------------------------------
# 轨迹事件（steps.jsonl）：公共字段与类型专属字段分离（discriminated union）
# ---------------------------------------------------------------------------


class EventBase(BaseModel):
    """所有事件的公共字段。"""

    model_config = ConfigDict(frozen=True)

    run_id: str
    step_id: str
    seq: int
    timestamp: datetime  # 必须带时区，canonical JSON 规则见 spec 7.1


class TaskStartEvent(EventBase):
    event_type: Literal["task_start"] = "task_start"
    task_id: str


class ModelOutputEvent(EventBase):
    """模型输出（M0 中为预设内容；M3 中为真实模型生成）。"""

    event_type: Literal["model_output"] = "model_output"
    content: str
    preset: bool  # True 表示 M0 预设，非现场生成


class ToolCallEvent(EventBase):
    event_type: Literal["tool_call"] = "tool_call"
    tool_name: str
    arguments: dict[str, Any]


class ToolResultEvent(EventBase):
    """工具原始返回（注入后）。"""

    event_type: Literal["tool_result"] = "tool_result"
    tool_name: str
    result: Any = None  # surface_as=raise_exception 时为 None
    error: str | None = None  # 异常类型名，如 "TimeoutError"
    injected: bool = False  # 本结果是否被故障注入改写


class InjectionEvent(EventBase):
    """故障注入事实记录：注入前后内容都记录，供 injection_applied 判定。"""

    event_type: Literal["injection"] = "injection"
    injection_point: InjectionPoint
    fault_type: FaultType
    surface_as: SurfaceAs
    original: Any = None
    replacement: Any = None
    raised: str | None = None
    applied: bool  # 注入是否真实生效（内容确实按 FaultSpec 改变）


class RunEndEvent(EventBase):
    event_type: Literal["run_end"] = "run_end"
    # 框架返回给调用方的最终信号：completed / failed
    framework_outcome: Literal["completed", "failed"]
    final_answer: str | None = None


StepEvent = Annotated[
    TaskStartEvent | ModelOutputEvent | ToolCallEvent | ToolResultEvent | InjectionEvent | RunEndEvent,
    Field(discriminator="event_type"),
]


# ---------------------------------------------------------------------------
# Oracle 判定记录（oracle.jsonl，每次运行每层一条）
# ---------------------------------------------------------------------------


class OracleJudgement(BaseModel):
    """单个评价层的判定结果，附带证据与原因字段。

    not_applicable / inconclusive 的原因字段规则见 spec 第 4、5 节：
    - 每次运行、每层只记一个主原因；
    - not_applicable 与两种 inconclusive 原因分别计数，不得合并。
    """

    run_id: str
    layer: TargetLayer
    verdict: FrameworkVerdict | ModelVerdict
    not_applicable_reason: NotApplicableReason | None = None
    inconclusive_reason: InconclusiveReason | None = None
    oracle: OracleSpec
    evidence: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


# ---------------------------------------------------------------------------
# run.json 运行清单
# ---------------------------------------------------------------------------


class VersionInfo(BaseModel):
    """版本与可复算字段（spec 第 7 节、NAMING 第 7 节）。

    字段不适用或当前不存在时显式写 None 并在 null_reasons 记录原因，
    不能省略字段或编造 commit。
    """

    faultlattice_commit: str | None = None
    host_package_version: str | None = None
    host_commit: str | None = None
    python_version: str
    dependency_lock_hash: str | None = None
    model_id: str | None = None
    sampling_params: dict[str, Any] | None = None
    null_reasons: dict[str, str] = Field(default_factory=dict)


class RunManifest(BaseModel):
    """run.json 的结构：运行级配置、版本、任务和预注册预期。"""

    run_id: str
    created_at: datetime
    task: TaskDefinition  # 预注册声明原样复制
    versions: VersionInfo
    injection_applied: bool
    observation_status: ObservationStatus
    model_invoked: bool = False  # 模型层是否实际被调用（M0–M2 恒为 False）
    # 运行所在目录相对仓库根的路径，便于报告引用
    run_dir: str
