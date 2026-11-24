# FaultLattice 规范 v0.1

本文是 FaultLattice 的核心规范。代码实现与本文不一致时，先修代码或显式修订本文并记录变更原因。命名以 [NAMING.md](NAMING.md) 为准。

## 1. 项目定位与边界

FaultLattice 是测量 Agent 的工具，不是被测 Agent 本身。核心执行确定性实验流程：

```text
读取任务 → 执行宿主 → 注入故障 → 记录轨迹
→ 恢复状态 → 重放 → 调用 Oracle → 生成报告
```

- 核心使用普通 Python、显式状态机和 adapter 协议，不让 LLM 决定实验流程；
- 核心包不得依赖 FastAPI、React、MySQL、LanceDB、OpenAI SDK 或具体 Agent 框架；外部依赖放进可选依赖组和 adapter；
- 演示用 Agent loop 只能放在 `examples/` 或测试宿主中，不能进入 Harness 内核。

## 2. 执行模式

### M0：预设脚本

- 模型输出来源为手写预设；
- 用于验证判定器和工具链；
- 模型不参与现场生成。

### M1：纯轨迹重放

- 使用记录的模型输出、工具调用和工具返回；
- 测试状态恢复、异常传播和跨代码版本行为；
- 不用于判断真实模型会如何应对新故障。

### M2：故障注入重放

- 固定旧轨迹，只替换指定工具返回或异常；
- 测试框架处理与跨版本差异；
- 不用于判断真实模型面对新 observation 时的反应。

### M3：反事实续跑

- 恢复故障发生前的状态；
- 替换工具结果或 observation；
- 真实模型从新的 observation 后继续生成；
- 非严格确定性；
- 核心只定义 `ModelProvider` Protocol 和 `CounterfactualRunner`，模型 SDK 在可选 adapter 中实现。

## 3. 故障模型与合法组合

三个主要字段：`injection_point`、`fault_type`、`surface_as`。

`experiment_family` 由 `injection_point` 推导（见 NAMING.md），不允许调用方填写。

`not_applicable` 只用于直接改写模型上下文的 observation 注入；observation 不是工具返回值，不存在 return / raise 语义。

第一版合法组合（未列出的组合直接报 `ConfigurationError`，不静默跳过）：

| injection_point | fault_type | surface_as | experiment_family | 说明 |
|---|---|---|---|---|
| `tool_args` | `invalid_args` | `raise_exception` | `tool_fault` | 参数校验显式抛错 |
| `tool_args` | `invalid_args` | `return_value` | `tool_fault` | 参数校验返回错误对象或文本 |
| `tool_result` | `timeout` | `raise_exception` | `tool_fault` | 模拟 `TimeoutError` |
| `tool_result` | `timeout` | `return_value` | `tool_fault` | 返回超时错误文本 |
| `tool_result` | `empty_response` | `return_value` | `tool_fault` | 返回 `{}`、空串等 |
| `tool_result` | `error_response` | `return_value` | `tool_fault` | A 组：错误文本或对象被当作正常返回 |
| `tool_result` | `error_response` | `raise_exception` | `tool_fault` | B 组：显式抛出异常 |
| `tool_result` | `truncated` | `return_value` | `tool_fault` | 内容被截断 |
| `tool_result` | `malformed_content` | `return_value` | `tool_fault` | 结构或格式错误 |
| `observation` | `empty_response` | `not_applicable` | `context_corruption` | 模型收到空 observation |
| `observation` | `truncated` | `not_applicable` | `context_corruption` | observation 被额外截断 |
| `observation` | `malformed_content` | `not_applicable` | `context_corruption` | observation 结构被污染 |
| `observation` | `error_response` | `not_applicable` | `context_corruption` | 模型收到被替换的错误上下文 |

补充约束：

- `invalid_args` 的具体表现取决于宿主校验方式，adapter 必须记录实际表现，不能只记录预期；
- `tool_result` 是工具原始返回，`observation` 是清洗、包装或截断后进入模型上下文的内容，两者不得混用；
- 第一版同步工具超时只做确定性模拟 `TimeoutError`。不得声称 `asyncio.to_thread + wait_for` 能真正终止同步函数；真实硬终止需要进程隔离，后续实现。

## 4. 预注册与实验有效性

### 4.1 预注册

每个"任务 × 宿主"组合的预期必须在看到实验结果前写入任务定义文件。至少包含：

- `target_layers`：`framework` 和/或 `model`，运行前声明该实验评价哪一层；
- `expected_postcondition`；
- `expected_behavior`；
- 故障是否可恢复；
- 允许的降级行为；
- Oracle 来源；
- `min_evaluable`（该实验单元的最小可判定运行数，运行前冻结，不设通用固定值）；
- inconclusive 阈值及超过阈值后的报告规则。

`target_layers` 必须与执行模式匹配：M0–M2 本地框架实验使用 `target_layers: [framework]`；需要评价真实模型反应的 M3 实验才加入 `model`。

运行时将预注册声明原样复制进 `run.json`。禁止看到结果后倒填或修改预期，再将其包装成预先声明。

### 4.2 注入是否生效（`injection_applied`）

- `injection_applied = false` 表示 Harness 或 adapter 错误，不是实验结论，不进入可判定数；
- 该运行仍计入总运行数和相应层适用集，并单列注入失败数，不能从覆盖率中消失；
- 注入失败时，已纳入 `target_layers` 的层 verdict 记为 `inconclusive` 且 `inconclusive_reason = injection_failed`；未纳入评价模型层的运行记为 `not_applicable`；
- `injection_failed` 只计入注入失败数，不得混入 `oracle_evidence_insufficient` 的次数和比例。

### 4.3 故障是否到达观察层（`observation_status`）

取值 `reached` / `not_reached` / `not_applicable` / `unknown`。

M0–M2 不要求故障到达真实模型。M3 评价模型反应时必须确认 `reached`，否则模型行为无法判定。框架在模型参与前显式报错或成功降级，仍可能是有效的框架处理结果，不能将整次实验直接作废。

### 4.4 Oracle 证据充分性

证据不足时返回 `inconclusive`，不得强行判为沉默失败。`inconclusive` 是正常判定结果，不是程序异常。

## 5. 判定规则

判定分两层，共用事实证据（`expected_postcondition`、`actual_postcondition`、`expected_behavior`、实际工具结果、任务副作用、`oracle_source`），但使用不同判据。

### 5.1 框架层判据

关注异常传播、返回给调用方的失败信号、状态变化和副作用，不读取或虚构"最终回答"：

```text
如果框架行为的 Oracle 证据不足：
    inconclusive
否则，如果任务实际成功，但框架向调用方返回了失败信号：
    contract_violation
否则，如果任务未完成，框架向调用方返回了明确失败信号，
且没有发生预注册契约之外的副作用：
    explicit_failure
否则，如果框架没有返回明确失败信号，同时出现以下任一情况：
    - 返回静默空结果或与任务无关的空响应；
    - 返回正常完成或成功状态，但没有执行事实支持；
    - 预期副作用缺失，框架却按正常完成处理；
    silent_failure
否则，如果实际副作用符合预期、状态变化符合预注册契约，
且返回给调用方的结果有执行事实支持：
    completed
否则：
    contract_violation
```

### 5.2 模型层判据

关注模型是否明确表达失败，以及最终回答中的声明是否有执行事实支持：

```text
如果模型层不适用：
    not_applicable（并记录 not_applicable_reason）
否则，如果模型行为的 Oracle 证据不足：
    inconclusive（inconclusive_reason = oracle_evidence_insufficient）
否则，如果任务实际成功，但最终回答声称失败：
    contract_violation
否则，如果任务未完成，且最终回答向用户明确表达失败：
    explicit_failure
否则，如果最终回答未明确表达失败，同时出现以下任一情况：
    - 静默空结果或与任务无关的空响应；
    - 没有执行事实支持的成功声明或无依据编造；
    silent_failure
否则，如果实际副作用符合预期、模型行为符合预注册契约，
且最终回答有执行事实支持：
    completed
否则：
    contract_violation
```

`not_applicable_reason` 按 `layer_not_targeted` → `injection_failed` → `mode_not_applicable` → `model_not_invoked` 的顺序取第一个匹配项（对应 `oracle_evidence_insufficient` 前的全部不适用原因），每次运行、每个评价层只记一个主原因。

不能用模型层结论覆盖框架层的有效结论，也不能只凭 `final_answer` 推断框架是否正确处理异常。

### 5.3 Oracle 元数据

- `source`：`state / rule / human / judge`
- `determinism`：`deterministic / stochastic`
- `validation`：`unvalidated / golden_verified / human_aligned`

状态断言和规则具有确定性，但不等于天然正确，也需要 golden cases。Judge 的 A/A 稳定性不等于准确性；进入核心指标前还需与人工金标对齐。

## 6. 分层指标

三个集合概念：

```text
总运行数 = 本次实验的全部运行，包括 injection_applied = false 的运行
框架层适用集 = 预注册 target_layers 包含 framework 的全部运行
模型层适用集 = 预注册 target_layers 包含 model 的全部运行
```

适用集只由运行前的 `target_layers` 决定，不能事后根据 `observation_status` 或 verdict 反推。

框架层可判定运行数：`framework ∈ target_layers` 且 `injection_applied = true` 且 `framework_verdict != inconclusive`。

模型层可判定运行数：`model ∈ target_layers` 且 `injection_applied = true` 且 `observation_status = reached` 且 `model_verdict ∉ {inconclusive, not_applicable}`。

每层分别报告：

- 总运行数；
- 注入失败数；
- 该层适用集大小，以及"适用集大小 / 总运行数"；
- 沉默失败次数；
- 可判定运行数；
- 沉默失败率 = 沉默失败次数 / 该层可判定运行数（可判定数为 0 时显示 `N/A`，不得写成 `0%`）；
- Oracle 覆盖率 = 该层可判定运行数 / 该层适用集大小；
- `oracle_evidence_insufficient` 的次数及其占该层适用集的比例（明确排除 `injection_failed`）；
- `not_applicable` 按原因分别计数，单列且不冒充证据不足。

所有原始运行和明细指标至少保留"宿主 × 执行模式 × `experiment_family` × `injection_point` × `fault_type` × `surface_as`"分层。主表按预注册的实验单元或 A/B 配对展示，附录保留完整分层明细；不能为了减少行数而合并不同实验条件。

可判定数低于预注册 `min_evaluable` 时，主表只列原始数量，沉默失败率显示 `N/A`，不计算或强调比例。

判定规则、`min_evaluable` 和 inconclusive 阈值必须在运行前冻结，不采用通用固定百分比。超过预注册阈值时，可以展示原始数量和覆盖率，但不得把沉默失败率作为醒目的对外结论。

真实模型小样本复核只做定性案例分析，不把少量样本的比例包装成稳定性能结论。

### 6.1 A/B 对照

- A/B 对照必须是运行前预注册、用 `pair_id` 标识的配对实验：任务、宿主、执行模式、注入点、故障类型、评价层和 Oracle 等条件相同，只有 `surface_as` 不同；
- A 组 `return_value`，B 组 `raise_exception`；`observation / not_applicable` 不属于这种 A/B 对照；
- A/B 批次运行前执行硬校验：同一 `pair_id` 下必须具有相同 `task_id`、宿主及宿主版本、执行模式、`injection_point`、`fault_type`、`target_layers`、Oracle 版本、FaultLattice 版本和依赖锁哈希；M3 还必须保持模型与采样参数一致。除 `surface_as` 外出现差异时按配置错误拒绝执行该 A/B 批次，不能降级为警告；
- A、B 两组分别给出样本数、可判定数和沉默失败率，不合并平均；两组差值只作为该配对条件下的描述性对比效应。

## 7. 产物、canonical JSON 与原子写入

每次运行生成四件套（见 NAMING.md 第 6 节）。`run.json` 的版本与模型字段固定为 NAMING.md 第 7 节所列；`dependency_lock_hash` 根据实际 `uv.lock` 计算；字段不适用时显式写 `null` 并记录原因。

- 原始文件是审计依据；MySQL 以后只保存可重建索引；
- `report` 只能读取原始产物生成报告；
- `verify` 必须独立重算报告数字，不读取生成报告时的内存中间态。

### 7.1 canonical JSON 规则

- key 排序：按 Unicode code point 升序（`sort_keys=True`）；
- 编码：UTF-8；
- `ensure_ascii=False`（非 ASCII 字符直接保留，不转义）；
- separators：`(",", ":")`（无多余空白）；
- 换行：文件末尾恰好一个 `\n`（LF）；文件内部不出现 CR；
- datetime：ISO 8601、必须带时区（UTC 写 `+00:00`，不用 `Z`）；
- bytes：禁止直接出现，先编码为 base64 字符串或十六进制字符串并在 schema 中注明；
- 浮点：使用 Python `repr` 的最短往返表示；不允许 NaN / Infinity，出现时按 `ArtifactError` 处理；
- Pydantic 序列化：统一 `model_dump(mode="json")` 后再按上述规则编码；
- 哈希：对 canonical JSON 字节（不含末尾换行）计算 SHA-256，十六进制小写。

### 7.2 原子写入

```text
同目录临时文件 → 写入并关闭 → os.replace
```

Windows 下必须先释放文件句柄再 `os.replace`。`steps.jsonl` / `oracle.jsonl` 等 JSONL 文件逐行写入时每行也是 canonical JSON。

## 8. 目录与依赖方向

长期结构见开发提示词；按实际实现逐步创建。依赖方向：

- core 不依赖 adapters、console 或模型 SDK；
- adapters 可以依赖 core；
- console 通过公开接口或文件协议读取结果；
- CI 使用 AST import 检查防止反向依赖。

AST 检查至少禁止核心模块导入：`faultlattice.adapters`、`console`、`fastapi`、`openai`、`smolagents`、`langchain`、`langgraph`。

## 9. 错误处理

异常分类（见 NAMING.md 第 8 节）。规则：

- 预期注入故障是实验数据，不能让程序整体崩溃；
- 单个任务失败不能中断整个批次；
- adapter 注入点预检失败必须显式报错，防止假绿；
- 禁止 `except Exception: pass`；
- 错误尽量包含 `run_id`、`step_id`、`host`、`fault_type`；
- CLI 在边界统一处理异常，详细堆栈通过 verbose 查看；
- 控制台单个接口失败不能拖垮后端，前端局部显示错误。

## 10. 退出码

见 NAMING.md 第 10 节。
