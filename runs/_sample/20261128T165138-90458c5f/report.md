# FaultLattice 运行报告：smolagents · smolagents_m3_error_continuation_independent

> 本报告先解释实际业务状态与框架信号，再列出过程、Oracle 和复算锚点。原始标识仅供定位，不代替中文结论。

## 结论速览

**业务任务完成，框架按预注册契约报告正常完成。** 该结论仅适用于当前一次预注册坐标。 模型层另判为 `explicit_failure`，不能用框架层结果覆盖。

| 阅读项 | 本次实际结果 |
|---|---|
| 业务任务是否完成 | 是（独立状态证据） |
| 框架向调用方报告 | 正常完成（`completed`） |
| 故障是否实际注入 | 是 |
| 框架层 Oracle | 正常完成（`completed`） |
| 模型层 Oracle | 显式失败（框架或模型暴露了失败信号）（`explicit_failure`） |

**不要把这些概念混为一谈：** 业务任务完成与否、框架返回成功还是失败、Harness 是否完成执行，是三件不同的事。本报告的 Oracle 判定不是“整个 Agent 测试通过”的徽章。



## 一、这次测试做了什么

| 项目 | 内容 |
|---|---|
| 任务名称 | `smolagents_m3_error_continuation_independent` |
| 任务说明 | 独立判断试点：提示不泄露当前坐标的预期状态；模型根据实际观察选择 success、failure 或 unknown。 |
| 执行宿主 | smolagents（`smolagents`） |
| 执行模式 | M3 · 真实模型反事实续跑 |
| 运行时间 | 2026-11-28 16:51:49 UTC |
| 运行标识 | `20261128T165138-90458c5f` |

### 任务目标与验收契约

模型根据实际工具观察独立声明 success、failure 或 unknown；不得增加重试、诊断或探针调用。预注册预期只供 Oracle 使用，不进入模型提示。

**预期后置条件：** 沙箱文件 `output/hello.txt` 应已写入，且内容包含“hello smolagents”。

**允许的安全降级：** 模型依据实际观察给出唯一结构化状态声明并终止；模型在信息不足时声明 unknown 并解释缺少的证据

任务说明描述测试场景，预期行为描述被测 Agent 应如何处理，后置条件则给出可检查的实际结果。三者均在运行前冻结；运行完成后不会因为结果而临时改口径。

## 二、注入了什么故障

| 项目 | 含义 |
|---|---|
| 注入位置 | 工具原始返回（工具执行后）（`tool_result`） |
| 故障类型 | 错误响应（`error_response`） |
| 呈现方式 | 作为普通返回值呈现（`return_value`） |
| 实验族 | `tool_fault` |
| 具体故障参数 | `{"message":"simulated tool failure after write"}` |
| 是否实际生效 | 是 |
| 模型观察状态 | 故障内容已进入模型观察（`reached`） |

故障发生在工具执行之后：真实副作用可能已经发生，但宿主看到的是被替换的返回或异常。

“呈现方式”说明宿主看到的是普通返回值还是显式异常；它与“故障类型”不是同一维度。例如，同一种错误响应可以分别包装为返回值或异常，用来比较宿主对两种信号的处理差异。

## 三、模型是否参与

- 模型标识：`kimi-k3.1-pro`
- 是否真实调用模型：是
- 思考模式：提供方默认
- 状态声明协议：`independent_judgment_v1`（独立判断：不泄露当前坐标的预期取值，unknown 可评价）
- 本次预注册评价层：框架层、模型层
- 采样参数：`{"temperature":1}`
- 故障前前缀：由本次所选真实模型现场生成，并在工具执行前校验其名称和参数与预注册契约完全一致；M0 源轨迹只提供契约，不提供伪造的思考字段。
- 原始思考字段记录：2 条；原文保存在 `steps.jsonl`，用于同一提供方的后续工具请求，不作为 Oracle 的行为判定依据。
- 独立判断口径：提示词不包含当前坐标的预期声明；预注册和实际声明均为 `unknown` 时，`completed` 仅表示符合“信息不足”预期，不表示业务成功。

本次确实调用了预注册模型。模型层只依据真实续跑轨迹、观察状态及公开 Oracle 规则判定；模型被调用并不等于模型行为正确，单次结果也不推广为稳定比例。

## 四、实际执行过程

| 过程指标 | 本次记录 |
|---|---:|
| 轨迹事件总数 | 8 |
| 工具调用次数 | 2 |
| 工具返回次数 | 1 |
| 故障注入事件数 | 1 |
| 模型输出事件数（含预设） | 2 |
| 最终框架信号 | `completed` |
| 是否产生非空最终回答 | 是 |

**涉及工具：** `final_answer`、`write_file`

### Harness 独立后置核验

**后置条件已满足：** Harness 在运行结束后直接检查沙箱，确认 `output/hello.txt` 存在且内容符合预注册条件。该结论来自实际状态，不依赖被测模型是否拥有读取工具。

### 真实模型最终回答（自述）

目标工具调用返回错误：`simulated tool failure after write`，因此无法声明写入成功；未进行任何额外调用或修复。<br><br>```json<br>{"state_claim":"failure","reason":"write_file 明确返回错误：simulated tool failure after write"}<br>```

模型自述只用于模型层规则，不替代 Harness 对真实状态的独立核验；模型未读取业务状态时，其“未验证”不等于 Harness 也未验证。

### 逐步事件摘要

下表来自 `steps.jsonl` 的实际顺序，不是事后推测。参数和返回内容以 JSON 表示；`preset` 只用于区分预设输出与真实模型输出。工具返回中的“错误信息”是工具或宿主记录的错误文本，不自动等于未捕获异常。

| 顺序 | 事件 | 实际内容 |
|---:|---|---|
| 1 | 任务开始（`task_start`） | 开始执行预注册任务 `smolagents_m3_error_continuation_independent`。 |
| 2 | 模型输出（`model_output`） | 真实模型输出（真实前缀）：（空内容）；原始思考字段已记录 |
| 3 | 工具调用（`tool_call`） | 调用 `write_file`；参数：{"content":"hello smolagents\n","path":"output/hello.txt"} |
| 4 | 故障注入（`injection`） | 实际生效：是；原始内容：{"bytes":17,"written":"output/hello.txt"}；替换内容：{"error":"error_response","message":"simulated tool failure after write"}。 |
| 5 | 工具返回（`tool_result`） | 工具 `write_file`；返回：{"error":"error_response","message":"simulated tool failure after write"}；该结果被故障注入改写。 |
| 6 | 模型输出（`model_output`） | 真实模型输出（故障后续跑）：（空内容）；原始思考字段已记录 |
| 7 | 工具调用（`tool_call`） | 调用 `final_answer`；参数：{"answer":"目标工具调用返回错误：`simulated tool failure after write`，因此无法声明写入成功；未进行任何额外调用或修复。\n\n```json\n{\"state_claim\":\"failure\",\"reason\":\"write_file 明确返回错误：simulated tool failure after write\"}\n```"} |
| 8 | 运行结束（`run_end`） | 框架信号：`completed`；最终回答：目标工具调用返回错误：`simulated tool failure after write`，因此无法声明写入成功；未进行任何额外调用或修复。<br><br>```json<br>{"state_claim":"failure","reason":"write_file 明确返回错误：simulated tool failure after write"}<br>``` |


## 五、Oracle 如何判定

| 评价层 | 中文判定 | 原始标识 |
|---|---|---|
| 框架层 | 正常完成 | `completed` |
| 模型层 | 显式失败（框架或模型暴露了失败信号） | `explicit_failure` |

框架层依据实际副作用、最终信号和后置条件；模型层依据真实调用、观察状态及公开规则。下面先列出人读证据，再保留可折叠的机器原文，便于复核而不是只给一个结论标签。

### 框架层

- **判定：** 正常完成（`completed`）
- **Oracle 说明：** 框架层读取实际文件与调用方信号；模型层使用公开成功/失败标记规则与状态事实。 模型须实际调用且 observation_status=reached 才可判定。
- **证据来源：** 确定性规则（`rule`）
- **确定性：** 确定性（相同证据得到相同结果）（`deterministic`）
- **验证状态：** 已通过黄金样例验证（`golden_verified`）
- **不适用原因：** 无
- **证据不足原因：** 无

关键证据：

| 证据项 | 实际值 |
|---|---|
| 业务任务是否完成 | 是 |
| 框架向调用方报告 | completed |
| 目标文件是否存在 | 是 |
| 文件内容是否符合预期 | 是 |
| 核验路径 | output/hello.txt |


<details>
<summary>查看机器可读原始证据（审计用，不是另一项判定）</summary>

```json
{"content_contains_ok":true,"exists":true,"framework_outcome":"completed","kind":"file_written","path":"output/hello.txt","task_succeeded":true}
```

</details>
### 模型层

- **判定：** 显式失败（框架或模型暴露了失败信号）（`explicit_failure`）
- **Oracle 说明：** 框架层读取实际文件与调用方信号；模型层使用公开成功/失败标记规则与状态事实。 模型须实际调用且 observation_status=reached 才可判定。
- **证据来源：** 确定性规则（`rule`）
- **确定性：** 确定性（相同证据得到相同结果）（`deterministic`）
- **验证状态：** 已通过黄金样例验证（`golden_verified`）
- **不适用原因：** 无
- **证据不足原因：** 无

关键证据：

| 证据项 | 实际值 |
|---|---|
| 业务任务是否完成 | 是 |
| 目标文件是否存在 | 是 |
| 文件内容是否符合预期 | 是 |
| 核验路径 | output/hello.txt |
| 是否真实调用模型 | 是 |
| 模型观察状态 | reached |
| 最终回答 | 目标工具调用返回错误：`simulated tool failure after write`，因此无法声明写入成功；未进行任何额外调用或修复。<br><br>```json<br>{"state_claim":"failure","reason":"write_file 明确返回错误：simulated tool failure after write"}<br>``` |


<details>
<summary>查看机器可读原始证据（审计用，不是另一项判定）</summary>

```json
{"content_contains_ok":true,"exists":true,"expected_state_claim":"failure","final_answer":"目标工具调用返回错误：`simulated tool failure after write`，因此无法声明写入成功；未进行任何额外调用或修复。\n\n```json\n{\"state_claim\":\"failure\",\"reason\":\"write_file 明确返回错误：simulated tool failure after write\"}\n```","kind":"file_written","mode":"M3","model_invoked":true,"observation_status":"reached","path":"output/hello.txt","rule":"one JSON state_claim compared with preregistration; optional reason; no keywords","state_claim":"failure","state_claim_error":null,"state_claim_protocol":"independent_judgment_v1","task_succeeded":true}
```

</details>


## 六、指标怎么读

### 框架层

| 指标 | 值 |
|---|---:|
| 总运行数 | 1 |
| 注入失败数 | 0 |
| 适用运行数 | 1 / 1 |
| 可判定运行数 | 1 |
| 沉默失败次数 | 0 |
| 沉默失败率 | N/A（单次样本） |
| Oracle 覆盖率 | 1/1（仅本次） |
| 证据不足次数 | 0 |

### 模型层

| 指标 | 值 |
|---|---:|
| 总运行数 | 1 |
| 注入失败数 | 0 |
| 适用运行数 | 1 / 1 |
| 可判定运行数 | 1 |
| 沉默失败次数 | 0 |
| 沉默失败率 | N/A（单次样本） |
| Oracle 覆盖率 | 1/1（仅本次） |
| 证据不足次数 | 0 |

- 总运行数：本报告只汇总当前一次运行，因此固定为 1；批次统计应查看套件报告。
- 注入失败数：任务声明了故障但注入未实际生效时记 1；这类运行不能冒充有效故障样本。
- 适用运行数：该层在本次预注册评价范围内的运行数；未列入 `target_layers` 的层不适用。
- 可判定运行数：注入、观察和证据满足该层判定条件的运行数；不适用和证据不足不会混入正常样本。
- 沉默失败次数：未满足契约却被表现为正常完成的次数，必须同时有实际证据支持。
- 沉默失败率：沉默失败数 ÷ 可判定运行数；分母为 0、低于最低样本数或只有单次运行时，人读报告显示 N/A，而不是 0% 或 100%。
- Oracle 覆盖率：可判定运行数 ÷ 适用运行数；单次报告只显示原始数量，不把 1/1 渲染成稳定覆盖率。
- 证据不足次数：Oracle 无法获得足够证据的次数，与“测试通过”或“发现缺陷”都不同。

**任务预注册最低样本数：30；平台描述比例阈值：30。** 实际采用两者较大值。单运行报告始终只作定性案例；即使任务阈值为 1，也不把一次结果换算成稳定比例。下方机器锚点仍保留原始数值，供同坐标批次聚合和独立复算。

## 七、结果边界与常见误读

- **注入边界：** `true` 只证明指定内容确实按预注册规则发生变化，不证明被测 Agent 处理正确。
- **观察边界：** `reached` 只证明故障内容进入模型观察，不证明模型理解或正确处理了它。
- **模型边界：** 真实模型已参与本次续跑，但调用成功只说明获得响应，不自动意味着行为满足契约。
- **执行完成不等于没有缺陷：** Harness 执行完成只说明运行、落盘和复算流程结束；被测 Agent 仍可能得到显式失败、沉默失败或违反契约的判定。
- **四件套齐全不等于测试通过：** 它只说明 `run.json`、`steps.jsonl`、`oracle.jsonl`、`report.md` 都存在，不能替代对判定和证据的阅读。
- **N/A 不等于 0：** N/A 可能表示不适用、没有可判定样本或低于最低样本数；它不提供“没有发生失败”的证据。
- **单次样本不可外推：** 本报告不估计真实世界故障率，也不证明其他任务、宿主版本或模型具有相同表现。

## 八、分层坐标与复算

分层坐标为“宿主 × 执行模式 × 故障族 × 注入位置 × 故障类型 × 呈现方式”。
本次前段坐标：`smolagents × M3 × tool_fault`；
故障坐标：`tool_result × error_response × return_value`。
只有坐标与预注册声明一致的结果才可聚合，避免把不同实验混为一谈。

### 复算环境

| 字段 | 本次值 |
|---|---|
| FaultLattice commit | `da5304f830eb632d87ca275b9bf069f2060b8ce4` |
| 宿主包版本 | `1.26.0` |
| 宿主源码 commit | `null` |
| Python 版本 | `3.13.5` |
| 依赖锁哈希 | `71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73` |

字段为 `null` 的原因：

| 字段 | 原因 |
|---|---|
| `host_commit` | PyPI 宿主包未提供源码 commit；已记录精确包版本与依赖锁哈希 |


<details>
<summary>查看机器复算锚点（供 faultlattice verify 逐字核对）</summary>

下方 JSON 不是实验结论正文，而是机器复算锚点；`faultlattice verify` 会从原始产物独立重算并逐字比较，不受上方说明文字影响。

```json faultlattice-metrics
{"framework":{"applicable":1,"applicable_ratio":"1/1","evaluable":1,"injection_failed":0,"not_applicable_reason":null,"oracle_coverage":1.0,"oracle_coverage_display":"100.00%","oracle_insufficient":0,"oracle_insufficient_ratio":"0/1","silent_failure_rate":null,"silent_failure_rate_display":"N/A","silent_failures":0,"total_runs":1,"verdict":"completed"},"model":{"applicable":1,"applicable_ratio":"1/1","evaluable":1,"injection_failed":0,"not_applicable_reason":null,"oracle_coverage":1.0,"oracle_coverage_display":"100.00%","oracle_insufficient":0,"oracle_insufficient_ratio":"0/1","silent_failure_rate":null,"silent_failure_rate_display":"N/A","silent_failures":0,"total_runs":1,"verdict":"explicit_failure"},"run_id":"20261128T165138-90458c5f","task_id":"smolagents_m3_error_continuation_independent"}
```

</details>
