# FaultLattice 命名登记（NAMING）

本文件登记项目中具有契约含义的名称。新增、改名、废弃名称时必须先更新本文件，再改代码。

## 1. 项目级名称

| 名称 | 取值 | 说明 |
|---|---|---|
| 展示名 | `FaultLattice` | 对外展示、文档标题 |
| 仓库名 | `faultlattice` | Git 仓库 |
| Python 包名 | `faultlattice` | `src/faultlattice/` |
| CLI 命令 | `faultlattice` | `pyproject.toml` 的 `[project.scripts]` |
| 英文副标题 | `Agent Reliability Harness & Evaluation Platform` | 固定文案 |

## 2. 执行模式（Execution Mode）

| 标识 | 名称 | 说明 |
|---|---|---|
| `M0` | 预设脚本 | 模型输出来源为手写预设，模型不参与现场生成 |
| `M1` | 纯轨迹重放 | 使用记录的模型输出、工具调用和工具返回 |
| `M2` | 故障注入重放 | 固定旧轨迹，只替换指定工具返回或异常 |
| `M3` | 反事实续跑 | 恢复故障前状态，真实模型从新 observation 继续生成 |

## 3. 故障模型字段

### `injection_point`

| 取值 | 说明 |
|---|---|
| `tool_args` | 注入在工具参数上 |
| `tool_result` | 注入在工具原始返回上 |
| `observation` | 注入在经过清洗、包装后进入模型上下文的内容上 |

### `fault_type`

`timeout` / `empty_response` / `truncated` / `malformed_content` / `error_response` / `invalid_args`

### `surface_as`

| 取值 | 说明 |
|---|---|
| `return_value` | 以正常返回值的形式呈现 |
| `raise_exception` | 以显式异常的形式呈现 |
| `not_applicable` | 仅用于 observation 注入（无 return / raise 语义） |

### `experiment_family`（由 `injection_point` 推导，不允许调用方填写）

| 推导规则 | 取值 |
|---|---|
| `tool_args` / `tool_result` | `tool_fault` |
| `observation` | `context_corruption` |

## 4. 判定与状态字段

### `framework_verdict`

`completed` / `explicit_failure` / `silent_failure` / `contract_violation` / `inconclusive`

### `model_verdict`

`completed` / `explicit_failure` / `silent_failure` / `contract_violation` / `inconclusive` / `not_applicable`

### `not_applicable_reason`（model_verdict = not_applicable 时必填）

`layer_not_targeted` / `injection_failed` / `mode_not_applicable` / `model_not_invoked`

判定顺序：`layer_not_targeted` → `injection_failed` → `mode_not_applicable` → `model_not_invoked` → `oracle_evidence_insufficient`，取第一个匹配项，每次运行每层只记一个主原因。

### `inconclusive_reason`

`injection_failed` / `oracle_evidence_insufficient`（两者分别计数，不得合并）

### `observation_status`

`reached` / `not_reached` / `not_applicable` / `unknown`

### `target_layers`

`framework` 和/或 `model` 的非空列表，运行前在预注册文件中声明。

## 5. Oracle 元数据

| 字段 | 取值 |
|---|---|
| `source` | `state` / `rule` / `human` / `judge` |
| `determinism` | `deterministic` / `stochastic` |
| `validation` | `unvalidated` / `golden_verified` / `human_aligned` |

## 6. 产物文件（每次运行的四件套）

```text
runs/<run_id>/
├── run.json
├── steps.jsonl
├── oracle.jsonl
└── report.md
```

公开样例目录固定为 `runs/_sample/<run_id>/`。

## 7. 版本与可复算字段（run.json）

`faultlattice_commit` / `host_package_version` / `host_commit` / `python_version` / `dependency_lock_hash` / `model_id` / `sampling_params`

字段不适用或不存在时显式写 `null` 并记录原因，不得省略或编造。

## 8. 异常类型

`ConfigurationError` / `AdapterCapabilityError` / `InjectionError` / `TraceFormatError` / `ReplayError` / `OracleError` / `ArtifactError`

## 9. A/B 对照

- 以 `pair_id` 标识的预注册配对；A 组 `surface_as = return_value`，B 组 `surface_as = raise_exception`；
- `observation / not_applicable` 不属于 A/B 对照；
- 除 `surface_as` 外的任何条件差异按配置错误拒绝执行。

## 10. 退出码

| 场景 | 退出码 |
|---|---|
| 实验成功执行（含发现 silent_failure） | `0` |
| Harness 自身配置 / adapter / 轨迹 / 写入错误 | 非零 |
| `verify` 复算失败 | 非零 |
| CI 回归门禁 | 按门禁配置决定 |
