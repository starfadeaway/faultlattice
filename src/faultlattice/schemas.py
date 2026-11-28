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

    kind 的取值由 Oracle 判定器解释：
    - file_written：params = {"path": 相对沙箱路径, "content_contains": 可选子串}
    - file_absent：params = {"path": 相对沙箱路径}，只证明目标文件不存在
    - host_state：由实现 StatefulHost 的适配器只读核验真实业务状态；
      params 必须包含人读 summary，具体观察证据不得包含凭据
    """

    model_config = ConfigDict(frozen=True)

    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class ModelSpec(BaseModel):
    """M3 真实模型的预注册配置；凭据只允许来自环境变量。"""

    model_config = ConfigDict(frozen=True)

    provider: Literal["openai_compatible"]
    model_id: str = Field(min_length=1)
    sampling_params: dict[str, Any] = Field(default_factory=dict)
    reasoning_mode: Literal["default", "enabled", "disabled"] = "default"


class TaskDefinition(BaseModel):
    """任务 × 宿主的预注册声明，运行前冻结并原样复制进 run.json。"""

    task_id: str
    description: str = ""
    host: str
    mode: ExecutionMode
    # 故障规范；M1 纯轨迹重放不注入故障，允许为 None
    fault: FaultSpec | None = None
    target_layers: list[TargetLayer] = Field(min_length=1)
    expected_postcondition: ExpectedPostcondition
    expected_behavior: str
    # 新运行必须显式冻结；None 仅用于读取旧版历史 run.json。
    expected_failure_signal: bool | None = None
    # 模型依据实际收到的工具观察应声明成功还是失败；与业务后置条件分开评价。
    # 新 M3 模型层运行必须显式冻结，历史空值不得回填成当时事实。
    expected_state_claim: Literal["success", "failure"] | None = None
    fault_recoverable: bool
    allowed_degradation: list[str] = Field(default_factory=list)
    oracle: OracleSpec
    inconclusive_threshold: float = Field(ge=0.0, le=1.0)
    inconclusive_reporting: str = ""
    min_evaluable: int = Field(ge=1)
    pair_id: str | None = None
    # M0 预设脚本；M3 的实际前缀由 counterfactual_source 的轨迹重建。
    script: list[dict[str, Any]] = Field(default_factory=list)
    model: ModelSpec | None = None
    counterfactual_source: str | None = None

    @model_validator(mode="after")
    def _check_mode_contract(self) -> TaskDefinition:
        if self.mode in (ExecutionMode.M0, ExecutionMode.M1, ExecutionMode.M2):
            if TargetLayer.MODEL in self.target_layers:
                raise ConfigurationError(
                    f"任务 {self.task_id}: 执行模式 {self.mode} 不产生真实模型反应，"
                    "target_layers 不得包含 model（spec 第 4.1 节）。"
                )
            if self.model is not None or self.counterfactual_source is not None:
                raise ConfigurationError("M0–M2 不得声明真实模型或 M3 源轨迹")
        else:
            if self.model is None or self.counterfactual_source is None:
                raise ConfigurationError("M3 必须预注册 model 与 counterfactual_source")
            if self.fault is None or self.fault.injection_point not in (
                InjectionPoint.TOOL_RESULT,
                InjectionPoint.OBSERVATION,
            ):
                raise ConfigurationError("M3 只支持 tool_result / observation 故障")
            unambiguous_failures = {
                FaultType.TIMEOUT,
                FaultType.EMPTY_RESPONSE,
                FaultType.TRUNCATED,
                FaultType.MALFORMED_CONTENT,
                FaultType.ERROR_RESPONSE,
            }
            if (
                self.expected_state_claim == "success"
                and self.fault.fault_type in unambiguous_failures
            ):
                raise ConfigurationError(
                    f"任务 {self.task_id}: 当前 Schema 不支持在 "
                    f"{self.fault.fault_type.value} 故障下预注册 expected_state_claim=success；"
                    "恢复类实验须先新增并验证显式恢复证据契约，不能仅靠同一故障类型放开 success"
                )
        return self


# ---------------------------------------------------------------------------
# 轨迹事件（steps.jsonl）：公共字段与类型专属字段分离（discriminated union）
# ---------------------------------------------------------------------------


class EventBase(BaseModel):
    """所有事件的公共字段。"""

    # 允许带诊断扩展字段，但判别类型、公共字段和类型专属必填字段必须验证。
    model_config = ConfigDict(frozen=True, extra="allow")

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
    reasoning_content: str | None = None  # 提供方原始思考字段，供后续工具轮次回传
    m3_phase: Literal["prefix", "continuation"] | None = None


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
    # 历史 replay 的人工补充预期必须显式留痕，不得冒充源运行预注册事实。
    manual_expectations: list[str] = Field(default_factory=list)
    # 运行所在目录相对仓库根的路径，便于报告引用；不得泄露本机绝对路径。
    run_dir: str
    # 新运行写入原始轨迹哈希；None 仅表示历史产物没有可回溯校验的哈希。
    steps_sha256: str | None = None
    oracle_sha256: str | None = None
    # Harness 异常保留原始事件与失败清单，但不伪造 Oracle 或完整四件套。
    execution_status: Literal["completed", "harness_failed"] = "completed"
    harness_error: dict[str, str] | None = None
