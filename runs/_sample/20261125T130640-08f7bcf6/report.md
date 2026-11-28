# FaultLattice 运行报告：smolagents · smolagents_observation_error

> 本报告先解释实际业务状态与框架信号，再列出过程、Oracle 和复算锚点。原始标识仅供定位，不代替中文结论。

## 结论速览

**业务任务完成，框架报告正常完成。** 该结论仅适用于当前一次预注册坐标。

| 阅读项 | 本次实际结果 |
|---|---|
| 业务任务是否完成 | 是（独立状态证据） |
| 框架向调用方报告 | 正常完成（`completed`） |
| 故障是否实际注入 | 是 |
| 框架层 Oracle | 正常完成（`completed`） |


**不要把这些概念混为一谈：** 业务任务完成与否、框架返回成功还是失败、Harness 是否完成执行，是三件不同的事。本报告的 Oracle 判定不是“整个 Agent 测试通过”的徽章。

> **旧口径警示：** 该历史运行没有机器可判定的 expected_failure_signal，框架层 verdict 仅按旧口径保留，不能用于新契约下的行为比较


## 一、这次测试做了什么

| 项目 | 内容 |
|---|---|
| 任务名称 | `smolagents_observation_error` |
| 任务说明 | 工具真实写入后，只把进入下一轮预设模型上下文的内容替换成错误文本，验证观察注入确实到达宿主上下文。 |
| 执行宿主 | smolagents（`smolagents`） |
| 执行模式 | M0 · 预设脚本执行 |
| 运行时间 | 2026-11-25 13:06:40 UTC |
| 运行标识 | `20261125T130640-08f7bcf6` |

### 任务目标与验收契约

原始工具结果和文件副作用保持不变，仅模型观察被替换；M0 预设最终回答不代表真实模型反应。

**预期后置条件：** 沙箱文件 `output/hello.txt` 应已写入，且内容包含“hello smolagents observation”。

**允许的安全降级：** 记录观察替换并按预设脚本结束

任务说明描述测试场景，预期行为描述被测 Agent 应如何处理，后置条件则给出可检查的实际结果。三者均在运行前冻结；运行完成后不会因为结果而临时改口径。

## 二、注入了什么故障

| 项目 | 含义 |
|---|---|
| 注入位置 | 模型观察（进入下一轮模型上下文前）（`observation`） |
| 故障类型 | 错误响应（`error_response`） |
| 呈现方式 | 不适用返回／异常语义（`not_applicable`） |
| 实验族 | `context_corruption` |
| 具体故障参数 | `{"message":"simulated corrupted observation"}` |
| 是否实际生效 | 是 |
| 模型观察状态 | 本次运行没有真实模型观察环节（`not_applicable`） |

故障只改变进入模型下一轮上下文的内容，不改写工具已经产生的真实副作用。

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
| 轨迹事件总数 | 6 |
| 工具调用次数 | 1 |
| 工具返回次数 | 1 |
| 故障注入事件数 | 1 |
| 模型输出事件数（含预设） | 1 |
| 最终框架信号 | `completed` |
| 是否产生非空最终回答 | 是 |

**涉及工具：** `write_file`

### Harness 独立后置核验

**后置条件已满足：** Harness 在运行结束后直接检查沙箱，确认 `output/hello.txt` 存在且内容符合预注册条件。该结论来自实际状态，不依赖被测模型是否拥有读取工具。

### 预设最终回答（非真实模型输出）

已写入 output/hello.txt。

这段文字来自运行前冻结的脚本，只用于驱动生产循环，不能用于评价模型能力。业务结论来自真实工具、生产状态和独立后置观察。

### 逐步事件摘要

下表来自 `steps.jsonl` 的实际顺序，不是事后推测。参数和返回内容以 JSON 表示；`preset` 只用于区分预设输出与真实模型输出。工具返回中的“错误信息”是工具或宿主记录的错误文本，不自动等于未捕获异常。

| 顺序 | 事件 | 实际内容 |
|---:|---|---|
| 1 | 任务开始（`task_start`） | 开始执行预注册任务 `smolagents_observation_error`。 |
| 2 | 工具调用（`tool_call`） | 调用 `write_file`；参数：{"content":"hello smolagents observation\n","path":"output/hello.txt"} |
| 3 | 工具返回（`tool_result`） | 工具 `write_file`；返回：{"bytes":29,"written":"output/hello.txt"}。 |
| 4 | 故障注入（`injection`） | 实际生效：是；原始内容："{'written': 'output/hello.txt', 'bytes': 29}"；替换内容："{'error': 'error_response', 'message': 'simulated corrupted observation'}"。 |
| 5 | 模型输出（`model_output`） | 预设脚本输出：已写入 output/hello.txt。 |
| 6 | 运行结束（`run_end`） | 框架信号：`completed`；最终回答：已写入 output/hello.txt。 |


## 五、Oracle 如何判定

| 评价层 | 中文判定 | 原始标识 |
|---|---|---|
| 框架层 | 正常完成 | `completed` |


框架层依据实际副作用、最终信号和后置条件；模型层依据真实调用、观察状态及公开规则。下面先列出人读证据，再保留可折叠的机器原文，便于复核而不是只给一个结论标签。

### 框架层

- **判定：** 正常完成（`completed`）
- **Oracle 说明：** 检查文件、原始工具结果、观察注入事件与宿主最终信号；不把预设输出当作模型评价。
- **证据来源：** 实际状态（`state`）
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

**预注册最低可判定样本数：1。** 单运行报告始终只作定性案例；即使该阈值为 1，也不把一次结果换算成稳定比例。下方机器锚点仍保留原始数值，供同坐标批次聚合和独立复算。

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
本次前段坐标：`smolagents × M0 × context_corruption`；
故障坐标：`observation × error_response × not_applicable`。
只有坐标与预注册声明一致的结果才可聚合，避免把不同实验混为一谈。

### 复算环境

| 字段 | 本次值 |
|---|---|
| FaultLattice commit | `630ee65341e495480827a9dad5f84961fa27550c` |
| 宿主包版本 | `1.26.0` |
| 宿主源码 commit | `null` |
| Python 版本 | `3.13.5` |
| 依赖锁哈希 | `24bb7ccb0c9d260b11b8e9e929eb48565c102b7d2aab6126e2b357d13f99399c` |

字段为 `null` 的原因：

| 字段 | 原因 |
|---|---|
| `host_commit` | PyPI 宿主包未提供源码 commit；已记录精确包版本与依赖锁哈希 |
| `model_id` | 本次运行不使用真实模型 |
| `sampling_params` | 本次运行不使用真实模型 |


<details>
<summary>查看机器复算锚点（供 faultlattice verify 逐字核对）</summary>

下方 JSON 不是实验结论正文，而是机器复算锚点；`faultlattice verify` 会从原始产物独立重算并逐字比较，不受上方说明文字影响。

```json faultlattice-metrics
{"framework":{"applicable":1,"applicable_ratio":"1/1","evaluable":1,"injection_failed":0,"not_applicable_reason":null,"oracle_coverage":1.0,"oracle_coverage_display":"100.00%","oracle_insufficient":0,"oracle_insufficient_ratio":"0/1","silent_failure_rate":null,"silent_failure_rate_display":"N/A","silent_failures":0,"total_runs":1,"verdict":"completed"},"model":null,"run_id":"20261125T130640-08f7bcf6","task_id":"smolagents_observation_error"}
```

</details>
