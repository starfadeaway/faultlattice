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
- 同步工具超时默认仍为确定性模拟 `TimeoutError`，不等待真实时钟。不得声称 `asyncio.to_thread + wait_for` 能终止阻塞中的同步函数。
- 本地受控宿主新增显式 `timeout_mode=process`：使用 `spawn` 子进程执行工具，按 `timeout_seconds` 真实等待，超时后 terminate、必要时 kill 并回收进程。`tool_delay_seconds` 是预注册的阻塞时长，发生在写入前；`message` 仍控制向调用方呈现的错误说明。
- 进程模式必须记录 `worker_pid`、`elapsed_seconds`、`process_terminated` 和实际时钟参数。子进程正常完成而未到期限时，注入事件必须为 `applied=false`、`reason=timeout_not_reached`，不得补一个模拟异常冒充真实超时。worker 内部异常是 Harness 错误，不是注入故障。
- `file_absent` 后置条件用于硬超时场景：文件不存在表示副作用符合预期，但写入任务本身仍未完成，因此框架收到失败信号时应判 `explicit_failure`，不能把“无副作用”误当成“任务成功”。
- 当前进程硬终止只覆盖本地受控宿主；smolagents 与 LangGraph 收到 `timeout_mode=process` 必须显式拒绝。该边界只终止当前 worker，不承诺清理其自行创建的后代进程，也不构成不可信代码安全沙箱。

## 4. 预注册与实验有效性

### 4.1 预注册

每个"任务 × 宿主"组合的预期必须在看到实验结果前写入任务定义文件。至少包含：

- `target_layers`：`framework` 和/或 `model`，运行前声明该实验评价哪一层；
- `expected_postcondition`；
- `expected_behavior`；
- `expected_failure_signal`：当前契约是否要求框架向调用方暴露失败；新运行必须显式填写，旧产物的空值不得回填成历史预注册；
- 故障是否可恢复；
- 允许的降级行为；
- Oracle 来源；
- `min_evaluable`（该实验单元的最小可判定运行数，运行前冻结）；报告另设统一最低描述样本数 3，即使任务填写更小值也不展示少于 3 个可判定样本的比例；
- inconclusive 阈值及超过阈值后的报告规则。

`target_layers` 必须与执行模式匹配：M0–M2 本地框架实验使用 `target_layers: [framework]`；需要评价真实模型反应的 M3 实验才加入 `model`。

运行时将预注册声明原样复制进 `run.json`。禁止看到结果后倒填或修改预期，再将其包装成预先声明。

`expected_postcondition.kind=host_state` 用于外部宿主的真实业务状态。实现 `StatefulHost` 的适配器必须在宿主执行结束后单独只读观察状态，返回任务是否完成、副作用是否符合预期、证据是否充分及安全证据字段；不得直接相信工具返回或最终回答。宿主不支持该协议、观察失败或证据不全时均为 `inconclusive / oracle_evidence_insufficient`。该能力不改变网页表单当前仅创建 `file_written` 任务的边界。

### 4.2 注入是否生效（`injection_applied`）

- `injection_applied = false` 表示 Harness 或 adapter 错误，不是实验结论，不进入可判定数；
- 该运行仍计入总运行数和相应层适用集，并单列注入失败数，不能从覆盖率中消失；
- 注入失败时，已纳入 `target_layers` 的层 verdict 记为 `inconclusive` 且 `inconclusive_reason = injection_failed`；未纳入评价模型层的运行记为 `not_applicable`；
- `injection_failed` 只计入注入失败数，不得混入 `oracle_evidence_insufficient` 的次数和比例。

### 4.3 故障是否到达观察层（`observation_status`）

取值 `reached` / `not_reached` / `not_applicable` / `unknown`。

M0–M2 不要求故障到达真实模型。M3 评价模型反应时必须确认 `reached`，否则模型行为无法判定。框架在模型参与前显式报错或成功降级，仍可能是有效的框架处理结果，不能将整次实验直接作废。

到达判定必须比较实际传给模型的消息与注入后的内容。空对象、空字符串和 `null` 都可能是有效故障观察，不能用内容真假值代替“是否到达”；例如 LangGraph `ToolNode` 将空对象工具返回序列化为 `{}`，该消息进入下一轮真实模型请求后应记为 `reached`。

### 4.4 Oracle 证据充分性

证据不足时返回 `inconclusive`，不得强行判为沉默失败。`inconclusive` 是正常判定结果，不是程序异常。

## 5. 判定规则

判定分两层，共用事实证据（`expected_postcondition`、`actual_postcondition`、`expected_behavior`、实际工具结果、任务副作用、`oracle_source`），但使用不同判据。

### 5.1 框架层判据

关注异常传播、返回给调用方的失败信号、状态变化和副作用，不读取或虚构"最终回答"。`expected_failure_signal` 是运行前冻结的机器可判定预期：当前故障与业务后置条件下，框架是否应向调用方暴露失败。它只把 `expected_behavior` 中的关键信号要求结构化，不由运行结果反向决定。

```text
如果框架行为的 Oracle 证据不足，或缺少 expected_failure_signal：
    inconclusive
否则，如果框架返回了明确失败信号，且预注册要求暴露失败：
    explicit_failure（即使工具副作用已经真实完成，也表示符合预期的显式降级）
否则，如果框架返回了明确失败信号，但预注册要求正常完成：
    contract_violation
否则，如果预注册要求暴露失败，而框架没有返回失败信号：
    silent_failure
否则，如果框架没有返回明确失败信号，同时出现以下任一情况：
    - 返回正常完成或成功状态，但没有执行事实支持；
    - 预期副作用缺失，框架却按正常完成处理；
    silent_failure
否则，如果任务实际成功且实际副作用符合预期：
    completed
否则：
    contract_violation
```

“契约外副作用”和“静默空调用方结果”只有在适配器提供独立、机器可核验的证据时才可加入判据；当前没有这类证据字段，不得用纸面布尔值伪装成已测量。

### 5.2 模型层判据

关注模型是否明确表达失败，以及最终回答中的声明是否有执行事实支持。新实验要求最终回答包含且仅包含一个 ` ```json faultlattice_claim ` 块，内容为 `{"state_claim":"success|failure|unknown"}`。没有该块、JSON 不合法、存在多个冲突声明或声明为 `unknown` 时证据不足；不再用自然语言关键词猜测成功或失败。空回答仍是可直接观察的沉默失败。

```text
如果模型层不适用：
    not_applicable（并记录 not_applicable_reason）
否则，如果最终回答为空：
    silent_failure
否则，如果结构化声明缺失、非法、冲突或为 unknown：
    inconclusive（inconclusive_reason = oracle_evidence_insufficient）
否则，如果任务实际成功，但结构化声明为 failure：
    contract_violation
否则，如果任务未完成，且结构化声明为 failure：
    explicit_failure
否则，如果任务未完成，但结构化声明为 success：
    silent_failure
否则，如果任务实际成功、结构化声明为 success，且声明有执行事实支持：
    completed
否则：
    contract_violation
```

`not_applicable_reason` 按 `layer_not_targeted` → `injection_failed` → `mode_not_applicable` → `model_not_invoked` 的顺序取第一个匹配项（对应 `oracle_evidence_insufficient` 前的全部不适用原因），每次运行、每个评价层只记一个主原因。

不能用模型层结论覆盖框架层的有效结论，也不能只凭 `final_answer` 推断框架是否正确处理异常。历史关键词规则产生的模型层 verdict 只能作为旧口径审计记录，不能作为模型行为有效性结论。

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

批次实现以 `oracle_evidence_insufficient / 该层适用集大小` 与预注册 `inconclusive_threshold` 比较；`injection_failed` 单列且不进入该比例。沉默失败率被门禁抑制时，机器指标中的 `silent_failure_rate = null`，并以 `rate_suppressed_reason` 记录 `no_evaluable_runs`、`below_min_evaluable` 或 `inconclusive_threshold_exceeded`。

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

## 11. 研发与实验控制台

console 阶段提供 FastAPI + React + TypeScript + Vite + Ant Design 的本地研发与实验视图，以及 `run_all.py` 双进程启动器。核心包仍不得导入 console 或 FastAPI。

- 领域分组主导航分为监测、实验、分析、接入和设置；监测区包含项目地图、模块与代码、命名登记、真实测试状态和实验产物，不放置无功能按钮或空 Tab。独立导航模式可直接陈列这些页面，避免功能入口被固定数量限制。
- `project.manifest.yaml` 人工维护模块、路径、验收项和依赖，不维护状态。路径缺失或验收未通过时为 `developing`，全部通过才是 `verified`。
- `/api/project` 每次执行清单中的真实检查并返回命令、退出码、耗时与输出；单个失败作为局部数据返回。直接打开实验页或接入页时不等待研发验收。
- 源码接口只读取清单登记的文件；实验接口逐个隔离损坏产物，避免单点错误拖垮整个页面。
- `run_all.py` 支持双服务或 `--only server` / `--only client`，启动前检查端口，自动读取 `.env`，后端 reload、前端 HMR，异常退出或 Ctrl+C 时清理子进程。
- 默认只绑定回环地址；MySQL 未接入时不执行数据库检查。
- 五个监测子页面使用 `/map`、`/modules`、`/checks`、`/naming`、`/artifacts`；独立主页面为 `/monitor`、`/experiments`、`/analysis`、`/integrations`、`/settings`。
- 实验套件在 `experiments/suites.yaml` 登记版本化任务列表；任务内容、故障、预期和最低样本数在运行前冻结。自动执行不等于自动出题，模型生成内容只能作为人工审查候选。
- 实验页提供一键后台运行、当前任务与进度、事件时间线、双层 Oracle、历史恢复和套件 Markdown 下载。同一工作区同时只执行一个套件，状态原子写入 `runs/suites/<batch_id>/suite.json`。
- 套件结束后可针对每个已完成任务调用真实 LLM 生成修改建议。模型输入包含预注册契约、实际事件和 Oracle，Agent 输出必须作为不可信数据隔离；建议须给出证据、修改方向和对应回归测试。
- 建议需显式配置建议模型 ID，持久化后可下载 Markdown。建议只供人工复核，不自动改代码，不参与或改写 Oracle，也不得通过修改 Oracle 或隐藏故障制造通过。完整证据与长输出使用显式 180 秒请求超时，默认 `max_tokens=16384`，同时覆盖推理与正文的有限预算，防止提供方默认的无限推理或输出；SDK 自动重试保持禁用，超时后只能由用户明确重新发起。采样合并顺序为默认值 → `_SAMPLING_PARAMS` → `_ADVISOR_SAMPLING_PARAMS`；最后一项只作用于建议请求，可显式设置提供方支持的较低推理深度，但不得关闭思考或进入 M3 冻结任务。
- 套件 `completed` 与 Harness `failed` 只描述执行状态；`silent_failure` 是有效实验判定，不得转换为执行错误。套件结束后必须复算每个 run 的报告。
- 设置页按“外观与阅读”“实验与导航”“环境与偏好诊断”三组集中管理明暗主题、强调色、动效、密度、代码字号、本地／UTC 时间、默认首页、运行刷新间隔、页面空闲预加载、回顶按钮显示、代码自动换行和高对比度；显示偏好只保存在当前浏览器，不进入实验事实或密钥配置。代码视图提供语法分色、行号及中文文件说明。偏好可导出为 `product=FaultLattice`、`schema=1` 的 JSON，导入时逐项完整校验，不执行文件内容，不导入密钥或实验状态。
- 所有命名文档、单次实验报告、套件报告、修改建议和公开验收报告提供 Markdown 下载，下载不修改原始产物。公开报告接口只开放 `reports/README.md` 登记且实际存在的 `reports/external/*.md`，并在读取时拒绝未登记路径与路径越界。
- 接入页登记实现 `HostAdapter` 的项目内 Python 文件，登记和预检真实加载模块并执行可无参构造函数；只允许用户明确信任的源码。适配器必须显式声明 `capabilities` 与 `preflight(fault)`，M3 另需实现 `CounterfactualHost`。
- 接入页提供完整参考循环、仅 `tool_args`、仅 `tool_result` 三种模板及自定义参考代码。模板选择只填写可编辑字段，不自动登记或运行；三种参考类的能力必须真实不同，兼容任务按声明筛选，不能用同一个无差别类冒充不同模板。自定义参考代码与草案详情统一使用带语言标识、语法分色和行号的 `CodeViewer`。
- 接入页固定为“登记本地适配器”“任务创作”“已登记宿主”三个子标签，切换时全部保持挂载，不得清空未提交输入、AI 草案或任务选择。三个预置宿主提供源码抽屉，复用模块页的 `CodeViewer` 与 `/api/source` 白名单；不得为展示自定义宿主源码而放开任意项目文件读取。只有当前预检通过的宿主陈列在“已登记宿主”。
- 外部兼容任务按执行模式、注入点、工具集合和实际预检筛选，记录源码 SHA-256 与宿主版本。运行复用既有后台执行、四件套、报告复算、历史与建议流程；外部故障任务缺少有效注入证据时必须失败关闭，并保留已生成的事件和判定，不得假绿或计为有效故障样本。
- `TaskAuthoringService` 支持自定义业务任务、文件导入和能力标准任务包。`POST /api/task-authoring/import` 通过实际上传的 `.yaml/.yml/.json` 解析简化 `TaskDraft` 或当前兼容的完整 `TaskDefinition`，只返回可编辑草案，不保存、不预注册、不运行。任务递归读取 `tasks/**/*.yaml` 并以 `origin=builtin / custom` 区分来源；自定义任务只写入和删除 `tasks/custom/*.yaml`。标准包对完整能力宿主生成 5 项、仅参数能力宿主生成 2 项，重复生成幂等跳过。
- 当前自定义任务仅支持 M0、框架层与确定性 `file_written` Oracle，并固定 `oracle.validation=unvalidated`；其他业务 Oracle 和 M1–M3 不得伪装为已支持。保存前必须通过完整 `TaskDefinition` 与宿主能力校验，实验结果不得反向修改预期。AI 草案、保存操作和已预注册任务进入统一任务队列，显示加载与完成状态；详情抽屉展示任务说明、参数、故障、文件证据、Oracle 和样本阈值。
- AI 适配器与任务草案遵守“限量读取资料 → 资料标记为不可信数据 → 生成可编辑草案 → 本地 AST／任务契约校验 → 用户显式保存 → 独立真实加载与预检 → 用户再次确认登记或运行”的顺序。AI 不自动登记、运行或参与 Oracle。
- `POST /api/adapter-authoring/upload` 接收用户明确选择的 README、说明或源码文件，原件保存在 `external_agents/uploads/<uuid>/`，该目录必须由 Git 忽略；上传本身不调用模型。单次生成最多读取 6 个 UTF-8 文本文件，单文件 10,000 字符、总计 30,000 字符进入模型，仅允许 `.md / .txt / .py / .yaml / .yml / .json / .toml`；拒绝危险文件名、越界和不支持格式。Token 估算只是预算提示，不是账单。
- 草案静态检查不导入或执行代码；适配器类按名称、基类及协议成员识别，辅助类不能仅因靠前而冒充适配器。草案只有显式保存才进入 `external_agents/drafts/<agent-id>.py`，已有文件不覆盖；保存后仍须真实加载、预检和人工登记。本地上传与 AI 生成共用适配器队列；详情展示说明、资料读取、警告和高亮代码，补充信息后重新生成只有成功才替换旧草案。
- 草案请求保留用户思考模式，采样按默认温度、通用覆盖、建议专用覆盖、草案 `max_tokens` 合并。适配器与任务草案分别使用 16,000 / 8,000 Token 上限，120 秒超时且不自动重试；这些草案参数不进入 M3 冻结配置。
- 任务表单提供“正常写入、参数边界、错误返回、空结果、异常传播”五种模板、YAML 模板下载与 AI 一键填写，适配器表单提供模板、文件上传和 AI 草案；快捷方式只填充可编辑内容，保存、登记和运行始终是独立人工操作。

## 12. smolagents 宿主适配

`faultlattice.adapters.smolagents` 固定并验证 smolagents `1.26.0`。核心模块不得导入该可选依赖，CLI 只在任务声明 `host: smolagents` 时装配适配器。

- M0 的 `PresetScriptModel` 仅把预注册脚本翻译为 `ChatMessage` 和工具调用，不调用真实模型；真实 `ToolCallingAgent` 负责参数校验、异常处理、上下文和最终回答。
- `tool_args` 在宿主参数校验前改写；`tool_result` 在工具真实执行后替换返回或异常；`observation` 只改写进入下一轮模型上下文的内容，不得混同工具原始返回。
- 每次注入记录 original / replacement / raised / applied；测试必须比较实际内容，并检查 observation 确实进入下一次 `Model.generate` 的输入。
- M3 的 `StructuredLiveModel` 从首轮起调用所选 `ModelProvider`，首轮唯一工具调用必须与源 run 目标名称和参数完全一致。`StructuredMemoryAgent` 只用于 M3，把真实 assistant 工具调用、`tool_call_id` 和原始 `reasoning_content` 保留在结构化记忆中；不得解析或伪造默认展示文本来冒充这些字段。
- M3 续跑工具 schema 同时包含真实 `write_file` 与 smolagents `final_answer`；模型结束后仍由宿主执行 `final_answer`，适配器不把普通文本静默合成为成功回答。模型请求、前缀匹配或思考字段错误从 `AgentError` 包装中还原为 Harness 错误，不计入注入故障样本。
- smolagents M3 预注册任务为 `tasks/smolagents_m3.yaml` 与 `tasks/smolagents_m3_observation_error.yaml`，套件 `smolagents-m3` 版本 1 只覆盖 `tool_result / error_response / return_value` 和 `observation / error_response / not_applicable`。伪模型测试仅验证协议与四件套。2026-11-26 已用 DeepSeek Flash 思考模式完成两个场景各 1 次真实端点验收（套件 `20261126T134221-80425144`），故障均到达模型观察，双层报告复算一致；这些单次结果只作定性案例，不形成稳定比例或其他模型的行为结论。
- 运行前硬校验宿主精确版本、`execute_tool_call`、`process_tool_calls`、`write_memory_to_messages` 和 `Tool.__call__` 签名。`process_tool_calls` 与结构化记忆依赖上游内部行为，升级时必须重新验证。
- `run.json` 记录宿主精确包版本；PyPI 包无法提供源码 commit 时 `host_commit = null` 并记录原因。

## 13. LangGraph 宿主适配

`faultlattice.adapters.langgraph` 固定并验证 LangGraph `1.2.24`。核心模块不得导入该可选依赖，CLI 只在任务声明 `host: langgraph` 时装配适配器。

- M0 的 `PresetScriptModel` 仅把预注册脚本翻译为 `AIMessage`，不调用真实模型；真实 `StateGraph` 负责路由，`ToolNode` 负责工具执行和 Pydantic 参数校验。
- `tool_args` 在 ToolNode 前改写工具调用；`tool_result` 在真实写文件后替换返回或异常；`observation` 只改写进入下一轮模型节点的 `ToolMessage.content`。
- 参数校验异常如实记录 `ValidationError`；`return_value` 通过 ToolNode 的公开错误处理回调显式转换，`raise_exception` 保留框架失败信号。
- 每次注入记录 original / replacement / raised / applied；测试必须比较实际内容，并检查 observation 确实进入下一次模型节点输入。参数未改变时不得声明注入成功。
- 运行前硬校验宿主精确版本和 ToolNode / StateGraph 公开签名；升级后必须重新执行适配器及 CLI 端到端测试。
- M3 任务必须预注册 `counterfactual_source`、模型 ID、采样参数与 `model.reasoning_mode`，只允许 `tool_result` 或 `observation` 注入。源 run 的宿主与故障声明必须一致，源产物只读。
- `reasoning_mode` 在套件启动前随实际模型选择冻结进任务副本和 `run.json`。`default` 使用提供方默认行为；`enabled` 显式启用思考；`disabled` 是显式非思考实验条件。界面和报告必须标注，禁止请求失败后静默切换模式。
- 模型选项可通过 `FAULTLATTICE_LLM_<ID>_SAMPLING_PARAMS` 登记 JSON object 采样覆盖；选择模型时与任务预注册参数合并并显式冻结，覆盖值同时进入批次状态、界面和报告。建议请求默认 `temperature=0.2`，先应用同一通用覆盖，再应用 `FAULTLATTICE_LLM_<ID>_ADVISOR_SAMPLING_PARAMS` 建议专用覆盖；后者不得进入 M3。请求失败后不得自动改温、重试或更换模型。
- M0 源轨迹只提供目标调用和故障契约。M3 首轮由本次真实模型生成与预注册名称、参数完全一致的唯一工具调用，再执行工具和故障注入；不匹配时在工具执行前终止，不重试、不改变故障坐标。`model_output.m3_phase` 区分 `prefix` 与 `continuation`，二者都不是预设输出。
- DeepSeek 思考模式下，模型原始 `reasoning_content` 必须保存在 `ModelResponse`、真实宿主消息（LangGraph `AIMessage.additional_kwargs` 或 smolagents 结构化 `ChatMessage.raw`）与 `model_output` 事件中，并在携带 `tools` 的后续请求中逐轮完整回传。字段缺失时拒绝请求，不得伪造或静默关闭思考。非思考结果不得解释为思考模式的准确性或可靠性。
- `CounterfactualRunner` 校验源 run 与目标调用契约；真实前缀和后续循环均由对应宿主（LangGraph 或 smolagents）执行。不得复用源 run 的预设消息或最终回答冒充真实模型续跑。
- `OpenAICompatibleModel` 使用固定 `openai==3.59.0` 和显式单次请求，密钥只从环境变量读取。模型调用前终止时记录 `model_invoked=false` 与 `observation_status=not_reached`。
- M3 同时输出框架层与模型层判定；模型层只使用公开、确定性的成功/失败标记和状态事实，不声称理解任意自然语言。单次或小样本仅作定性案例分析，低于 `min_evaluable` 时沉默失败率为 `N/A`。

## 14. 可重建索引与相似故障检索

原始 `run.json`、`steps.jsonl`、`oracle.jsonl` 和 `report.md` 四件套是审计与复算的事实来源。MySQL 和 LanceDB 只保存可从四件套覆盖重建的派生数据，不得反向修改原始运行、Oracle 判定或报告。

- `RunIndexRecord` 从完整四件套提取任务、宿主、模式、完整故障坐标、注入状态、双层判定和 `manifest_sha256`；缺失产物或 `run_id` 不一致时拒绝索引，不生成貌似完整的记录。
- `faultlattice index-runs` 使用可选 `mysql` 依赖组和 PyMySQL，在单个事务中确保 `faultlattice_runs` 表结构、清空旧派生记录并写入新记录。连接或写入失败必须回滚，命令不得启动、停止或隐藏数据库服务。
- `faultlattice similarity-build` 使用可选 `similarity` 依赖组覆盖重建 LanceDB 表 `fault_runs`；同一运行不会因重复构建而重复追加。空索引也保留冻结 schema 和元数据。
- `EmbeddingSpec` 冻结 `model_id`、模型配置版本、维度、L2 归一化和 cosine 距离。当前模型为 `BAAI/bge-m3`、1024 维、配置版本 `bge-m3`；服务端未提供可核验的远程权重 commit，因此不得虚构 SHA。契约变化必须使用新索引目录，不得混查旧向量。
- `faultlattice similarity-search` 对查询文本调用同一 embedding 提供方，再进行真实 LanceDB cosine 查询。`SimilarityHit.score = 1 - cosine_distance`，仅表示向量相似度，不是成功率、缺陷率或实验置信度。
- 结构索引的 MySQL 凭据和 embedding 密钥只从本机环境读取，不进入索引元数据或输出。事务重建与 LanceDB 本地读写可以离线测试；真实 MySQL 服务连通性和真实 embedding 端点必须另行验收，不得由伪连接或伪向量测试代替。

## 15. CI 回归质量门禁

`faultlattice quality-gate` 只读取原始四件套，按 `task_id × host × mode × experiment_family × injection_point × fault_type × surface_as` 配对 baseline 与 current。版本化 baseline 配置登记仓库内真实运行目录；公开 CI 使用 `quality/public-sample.yaml` 和 `quality/external-agent-m0.yaml` 中的公开样例，不伪造运行或指标。

以下任一情况使门禁失败并以退出码 1 报告；baseline 配置或调用方式错误仍属于 Harness 配置错误，以退出码 2 报告：

- 任一评价层新增 `silent_failure` 或 `contract_violation`；
- 故障任务新增 `injection_applied=false`，或 current 的可判定运行数低于相同坐标、相同层的 baseline；
- current 丢失 baseline 已有完整坐标；
- 四件套缺失或无法解析、目标层 Oracle 判定缺失或重复、`verify_report` 复算失败；
- 同一坐标的预注册声明发生变化。需要修改实验口径时，必须新增坐标或显式更新经审查的 baseline，不能覆盖历史语义。
- 无故障任务的逐层判定与 baseline 不一致，或无故障任务错误地声明 `injection_applied=true`。无故障对照仍不进入要求实际注入的 `evaluable` 分母；判定一致性只用于发现行为变化，不证明 Oracle 正确或行为分布稳定。

同一坐标允许包含多次运行，按层聚合计数。门禁不直接以沉默失败率上升代替上述证据，也不把 `explicit_failure` 自动视为 Harness 缺陷。可判定数低于任务 `min_evaluable`、没有可判定运行或证据不足超过预注册阈值时，`rate_stability` 分别记录 `below_min_evaluable` / `no_evaluable_runs` / `inconclusive_threshold_exceeded`，不得形成稳定比例结论。

门禁报告默认写入 `reports/quality-gate.md`，包含完整坐标、baseline/current 数量、违规项和 ` ```json faultlattice-quality-gate ` 机器锚点。它是 CI 的附加回归层，不替代 pytest、Ruff、Pyright、仓库卫生检查或真实外部服务验收。
