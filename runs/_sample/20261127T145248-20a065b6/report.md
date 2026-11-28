# FaultLattice 运行报告：Anchorline · anchorline-memory-result-ab

> 本报告先解释实际业务状态与框架信号，再列出过程、Oracle 和复算锚点。原始标识仅供定位，不代替中文结论。

## 结论速览

**业务任务实际完成，但框架向调用方报告失败。** 实际状态与调用方信号不一致，因此本次判为违反预注册契约；不能笼统写成“写入未验证”。

| 阅读项 | 本次实际结果 |
|---|---|
| 业务任务是否完成 | 是（独立状态证据） |
| 框架向调用方报告 | 明确失败（`failed`） |
| 故障是否实际注入 | 是 |
| 框架层 Oracle | 违反预注册契约（`contract_violation`） |


**不要把这些概念混为一谈：** 业务任务完成与否、框架返回成功还是失败、Harness 是否完成执行，是三件不同的事。本报告的 Oracle 判定不是“整个 Agent 测试通过”的徽章。

> **旧口径警示：** 该历史运行没有机器可判定的 expected_failure_signal，框架层 verdict 仅按旧口径保留，不能用于新契约下的行为比较


## 一、这次测试做了什么

| 项目 | 内容 |
|---|---|
| 任务名称 | `anchorline-memory-result-ab` |
| 任务说明 | 在相同预注册条件下调用 Anchorline 生产 memory_write 工具，把专用验收事实写入独立测试数据库； 工具真实提交后，将返回给宿主的结果替换为错误对象，核验真实记忆状态与调用方信号。 |
| 执行宿主 | Anchorline（`anchorline`） |
| 执行模式 | M0 · 预设脚本执行 |
| 运行时间 | 2026-11-27 14:52:48 UTC |
| 运行标识 | `20261127T145248-20a065b6` |

### 任务目标与验收契约

两组的生产工具都应实际写入并提交同一验收事实；注入只改变工具观察，不得撤销真实写入。 无论错误以普通返回值还是显式异常呈现，宿主都应返回明确失败信号，不得继续给出预设成功回答。

**预期后置条件：** 运行结束后由宿主适配器只读查询实际业务状态：独立测试数据库中 faultlattice.acceptance.ab 的当前值应与预注册配对验收文本一致

**允许的安全降级：** 宿主记录故障并向调用方返回明确失败信号，真实状态由独立查询核验

任务说明描述测试场景，预期行为描述被测 Agent 应如何处理，后置条件则给出可检查的实际结果。三者均在运行前冻结；运行完成后不会因为结果而临时改口径。

## 二、注入了什么故障

| 项目 | 含义 |
|---|---|
| 注入位置 | 工具原始返回（工具执行后）（`tool_result`） |
| 故障类型 | 错误响应（`error_response`） |
| 呈现方式 | 作为显式异常呈现（`raise_exception`） |
| 实验族 | `tool_fault` |
| 具体故障参数 | `{"message":"simulated Anchorline memory_write failure"}` |
| 是否实际生效 | 是 |
| 模型观察状态 | 本次运行没有真实模型观察环节（`not_applicable`） |

故障发生在工具执行之后：真实副作用可能已经发生，但宿主看到的是被替换的返回或异常。

“呈现方式”说明宿主看到的是普通返回值还是显式异常；它与“故障类型”不是同一维度。例如，同一种错误响应可以分别包装为返回值或异常，用来比较宿主对两种信号的处理差异。

## 三、模型是否参与

- 模型标识：`未使用模型`
- 是否真实调用模型：否（预设脚本不调用真实模型）
- 思考模式：不适用（本次未预注册真实模型）
- 本次预注册评价层：框架层
- 采样参数：`null（本次未使用真实模型采样参数）`


本次结果只用于评价宿主框架对故障的处理，不代表任何真实模型的行为表现。轨迹中的 `model_output` 若标记为 `preset=true`，表示它是预注册脚本内容，不是模型现场生成。

## 四、实际执行过程

| 过程指标 | 本次记录 |
|---|---:|
| 轨迹事件总数 | 5 |
| 工具调用次数 | 1 |
| 工具返回次数 | 1 |
| 故障注入事件数 | 1 |
| 模型输出事件数（含预设） | 0 |
| 最终框架信号 | `failed` |
| 是否产生非空最终回答 | 否 |

**涉及工具：** `memory_write`

### Harness 独立后置核验

**业务目标已完成：** 独立会话已查询事实 faultlattice.acceptance.ab.anchorline_memory_result_surface；当前值与预注册值完全一致。该结论来自运行结束后的独立只读状态观察。

### 预设最终回答（非真实模型输出）

本次未产生非空最终回答。

这段文字来自运行前冻结的脚本，只用于驱动生产循环，不能用于评价模型能力。业务结论来自真实工具、生产状态和独立后置观察。

### 逐步事件摘要

下表来自 `steps.jsonl` 的实际顺序，不是事后推测。参数和返回内容以 JSON 表示；`preset` 只用于区分预设输出与真实模型输出。工具返回中的“错误信息”是工具或宿主记录的错误文本，不自动等于未捕获异常。

| 顺序 | 事件 | 实际内容 |
|---:|---|---|
| 1 | 任务开始（`task_start`） | 开始执行预注册任务 `anchorline-memory-result-ab`。 |
| 2 | 工具调用（`tool_call`） | 调用 `memory_write`；参数：{"attribute":"anchorline_memory_result_surface","entity_id":"faultlattice.acceptance.ab","value":"Anchorline M0 paired tool-result surface A/B 2026-11-27"} |
| 3 | 故障注入（`injection`） | 实际生效：是；原始内容：{"content":"{\"fact_id\": \"4440aae6638a4920b267cd2c0bde13e2\", \"supersedes\": null, \"archived\": 0}","meta":{"archived":0,"fact_id":"4440aae6638a4920b267cd2c0bde13e2"},"ok":true}；替换内容：null；抛出异常：RuntimeError。 |
| 4 | 工具返回（`tool_result`） | 工具 `memory_write`；工具返回错误：RuntimeError；该结果被故障注入改写。 |
| 5 | 运行结束（`run_end`） | 框架信号：`failed`；最终回答：（无非空最终回答） |


## 五、Oracle 如何判定

| 评价层 | 中文判定 | 原始标识 |
|---|---|---|
| 框架层 | 违反预注册契约 | `contract_violation` |


框架层依据实际副作用、最终信号和后置条件；模型层依据真实调用、观察状态及公开规则。下面先列出人读证据，再保留可折叠的机器原文，便于复核而不是只给一个结论标签。

### 框架层

- **判定：** 违反预注册契约（`contract_violation`）
- **Oracle 说明：** 每组运行结束后用全新数据库会话读取同一事实；首次用于配对 A/B，尚未做黄金样例或人工对齐验证
- **证据来源：** 实际状态（`state`）
- **确定性：** 确定性（相同证据得到相同结果）（`deterministic`）
- **验证状态：** 尚未做黄金样例或人工对齐验证（`unvalidated`）
- **不适用原因：** 无
- **证据不足原因：** 无

关键证据：

| 证据项 | 实际值 |
|---|---|
| 证据是否充分 | 是 |
| 业务任务是否完成 | 是 |
| 框架向调用方报告 | failed |
| 独立状态观察 | 独立会话已查询事实 faultlattice.acceptance.ab.anchorline_memory_result_surface；当前值与预注册值完全一致 |
| 独立查询是否找到事实 | 是 |
| 事实当前值是否符合预注册 | 是 |
| 实际事实 ID | 4440aae6638a4920b267cd2c0bde13e2 |


<details>
<summary>查看机器可读原始证据（审计用，不是另一项判定）</summary>

```json
{"evidence_sufficient":true,"fact_found":true,"fact_id":"4440aae6638a4920b267cd2c0bde13e2","framework_outcome":"failed","kind":"host_state","observation_summary":"独立会话已查询事实 faultlattice.acceptance.ab.anchorline_memory_result_surface；当前值与预注册值完全一致","task_succeeded":true,"value_matches":true}
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



- 总运行数：本报告只汇总当前一次运行，因此固定为 1；批次统计应查看套件报告。
- 注入失败数：任务声明了故障但注入未实际生效时记 1；这类运行不能冒充有效故障样本。
- 适用运行数：该层在本次预注册评价范围内的运行数；未列入 `target_layers` 的层不适用。
- 可判定运行数：注入、观察和证据满足该层判定条件的运行数；不适用和证据不足不会混入正常样本。
- 沉默失败次数：未满足契约却被表现为正常完成的次数，必须同时有实际证据支持。
- 沉默失败率：沉默失败数 ÷ 可判定运行数；分母为 0、低于最低样本数或只有单次运行时，人读报告显示 N/A，而不是 0% 或 100%。
- Oracle 覆盖率：可判定运行数 ÷ 适用运行数；单次报告只显示原始数量，不把 1/1 渲染成稳定覆盖率。
- 证据不足次数：Oracle 无法获得足够证据的次数，与“测试通过”或“发现缺陷”都不同。

**预注册最低可判定样本数：2。** 单运行报告始终只作定性案例；即使该阈值为 1，也不把一次结果换算成稳定比例。下方机器锚点仍保留原始数值，供同坐标批次聚合和独立复算。

## 七、结果边界与常见误读

- **注入边界：** `true` 只证明指定内容确实按预注册规则发生变化，不证明被测 Agent 处理正确。
- **观察边界：** `not_applicable` 表示本次没有真实模型观察环节，常见于 M0–M2；它不是观察失败。
- **模型边界：** 本次没有真实模型参与，因此不能形成真实模型行为结论，也不能把预设输出当作模型能力证据。
- **执行完成不等于没有缺陷：** Harness 执行完成只说明运行、落盘和复算流程结束；被测 Agent 仍可能得到显式失败、沉默失败或违反契约的判定。
- **四件套齐全不等于测试通过：** 它只说明 `run.json`、`steps.jsonl`、`oracle.jsonl`、`report.md` 都存在，不能替代对判定和证据的阅读。
- **N/A 不等于 0：** N/A 可能表示不适用、没有可判定样本或低于最低样本数；它不提供“没有发生失败”的证据。
- **单次样本不可外推：** 本报告不估计真实世界故障率，也不证明其他任务、宿主版本或模型具有相同表现。

## 八、分层坐标与复算

分层坐标为“宿主 × 执行模式 × 故障族 × 注入位置 × 故障类型 × 呈现方式”。
本次前段坐标：`anchorline × M0 × tool_fault`；
故障坐标：`tool_result × error_response × raise_exception`。
只有坐标与预注册声明一致的结果才可聚合，避免把不同实验混为一谈。

### 复算环境

| 字段 | 本次值 |
|---|---|
| FaultLattice commit | `a94e2be8a1cd242b3090793e86a6e20db82d1c68` |
| 宿主包版本 | `0.1.0` |
| 宿主源码 commit | `null` |
| Python 版本 | `3.13.5` |
| 依赖锁哈希 | `71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73` |

字段为 `null` 的原因：

| 字段 | 原因 |
|---|---|
| `host_commit` | 外部源码副本未登记 commit；适配器源码 SHA-256 已保存在接入登记与批次记录中 |
| `model_id` | 本次运行不使用真实模型 |
| `sampling_params` | 本次运行不使用真实模型 |


<details>
<summary>查看机器复算锚点（供 faultlattice verify 逐字核对）</summary>

下方 JSON 不是实验结论正文，而是机器复算锚点；`faultlattice verify` 会从原始产物独立重算并逐字比较，不受上方说明文字影响。

```json faultlattice-metrics
{"framework":{"applicable":1,"applicable_ratio":"1/1","evaluable":1,"injection_failed":0,"not_applicable_reason":null,"oracle_coverage":1.0,"oracle_coverage_display":"100.00%","oracle_insufficient":0,"oracle_insufficient_ratio":"0/1","silent_failure_rate":null,"silent_failure_rate_display":"N/A","silent_failures":0,"total_runs":1,"verdict":"contract_violation"},"model":null,"run_id":"20261127T145248-20a065b6","task_id":"anchorline-memory-result-ab"}
```

</details>
