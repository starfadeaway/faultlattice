# FaultLattice 命名登记（NAMING）

本文件登记项目中具有契约含义的名称，并解释它们的用途、合法取值、相互区别和变更约束。它不是简单的词汇表：任务文件、运行轨迹、Oracle 判定、报告指标和控制台接口都以这里的名称为准。

新增、改名或废弃名称时，必须先更新本文件，再修改代码和测试。禁止为了让某次实验结果“更好看”而事后修改既有名称的含义；需要新语义时，应新增名称并递增相应套件或协议版本。

## 目录

- [1. 项目级名称](#1-项目级名称)
- [2. 执行模式（Execution Mode）](#2-执行模式execution-mode)
- [3. 故障模型字段](#3-故障模型字段)
- [4. 判定与状态字段](#4-判定与状态字段)
- [5. Oracle 元数据](#5-oracle-元数据)
- [6. 产物文件（每次运行的四件套）](#6-产物文件每次运行的四件套)
- [7. 版本与可复算字段（run.json）](#7-版本与可复算字段runjson)
- [8. 异常类型](#8-异常类型)
- [9. A/B 对照](#9-ab-对照)
- [10. 退出码](#10-退出码)
- [11. 批次聚合（Batch）](#11-批次聚合batch)
- [12. 研发与实验控制台（Console）](#12-研发与实验控制台console)
- [13. smolagents 宿主适配](#13-smolagents-宿主适配)
- [14. LangGraph 宿主与 M3 模型适配](#14-langgraph-宿主与-m3-模型适配)
- [15. 多模型配置与建议模型选择](#15-多模型配置与建议模型选择)
- [16. 标准实验矩阵](#16-标准实验矩阵)
- [17. 可重建索引与相似故障检索](#17-可重建索引与相似故障检索)
- [18. CI 回归质量门禁](#18-ci-回归质量门禁)
- [19. 任务创作与 AI 草案](#19-任务创作与-ai-草案)

## 1. 项目级名称

| 名称 | 固定取值 | 用在哪里 | 变更约束 |
|---|---|---|---|
| 展示名 | `FaultLattice` | 文档标题、控制台品牌、报告名称 | 只改变展示文案，不代表 Python 包或 CLI 同步改名 |
| 仓库名 | `faultlattice` | Git 仓库与项目元数据 | 不等同于用户机器上的目录名；界面不得把本机绝对路径当作项目身份 |
| Python 包名 | `faultlattice` | `src/faultlattice/` 与所有 `import faultlattice...` | 改名会同时影响导入、构建、测试和下游用户 |
| CLI 命令 | `faultlattice` | `pyproject.toml` 的 `[project.scripts]` | 修改命令前必须保留迁移说明并更新全部示例 |
| 英文副标题 | `Agent Reliability Harness & Evaluation Platform` | 控制台和项目介绍 | 用于说明定位，不是实验结果或性能声明 |

“Harness”指负责预注册、执行、故障注入、落盘和复算的测试设施；“被测 Agent”指接入 Harness 的宿主及其模型行为。二者必须分开：Harness 正常完成一次测试，不等于被测 Agent 没有缺陷。

### 命名变更的最小流程

1. 在本文件登记新名称、用途、合法取值和废弃关系。
2. 更新 `schemas.py` 中的枚举或 Pydantic 字段，避免文档与代码各自演化。
3. 更新任务 YAML、轨迹读写、报告渲染、控制台类型和中文文案。
4. 增加兼容或拒绝旧值的测试；不能让旧配置静默落入新语义。
5. 运行全量测试、Ruff、Pyright 和前端构建，再生成新的实验产物。

## 2. 执行模式（Execution Mode）

执行模式回答两个问题：模型输出从哪里来，以及故障之后是否让真实模型继续生成。模式在运行前写入任务 YAML，运行后不得根据结果切换。

| 标识 | 中文名称 | 输入与输出轨迹来源 | 是否现场调用真实模型 | 主要用途 |
|---|---|---|---|---|
| `M0` | 预设脚本执行 | 人工预注册的 `script`，按顺序产生工具调用和最终回答 | 否 | 验证真实宿主框架的参数校验、工具副作用、错误传播和最终信号 |
| `M1` | 纯轨迹重放 | 既有运行中记录的模型输出、工具调用和工具返回 | 否 | 在不引入故障的情况下检查重放一致性与轨迹契约 |
| `M2` | 故障注入重放 | 固定旧轨迹，只替换预注册位置的参数、返回或异常 | 否 | 在相同输入下比较有无故障时的宿主行为 |
| `M3` | 真实模型反事实续跑 | 源轨迹提供目标契约；本次真实模型建立前缀，故障后继续生成 | 是 | 评价模型收到错误或损坏观察后的实际续跑行为 |

### M0：预设脚本执行

M0 使用真实宿主代码和真实工具，但模型输出是预注册脚本。例如，`script` 可以先声明一次 `write_file` 工具调用，再声明一句“已写入”的最终回答。它能够稳定复现宿主处理流程，却不能证明真实模型会说出同样的话。

典型误区：看到轨迹里的 `model_output` 就以为调用了模型。M0 中该事件的 `preset=true`，`model_invoked=false`，模型层不得据此形成行为结论。

### M1：纯轨迹重放

M1 的重点是“相同输入能否按既定轨迹重放”，不是重新询问模型。它适合作为 M2 的对照和适配器回归检查。如果源轨迹本身缺少必要事件，应该报轨迹格式错误，而不是自动补写一段看似合理的内容。

### M2：故障注入重放

M2 保留旧轨迹的控制流，只改变预注册故障位置。它适合隔离宿主的错误处理差异。与 M3 的区别是：M2 故障后的回答仍来自旧轨迹，不能用于评价真实模型的应变。

### M3：真实模型反事实续跑

M3 从只读 M0 源 run 提取目标工具调用和故障契约，再由本次预注册模型现场生成完全匹配的真实前缀。源 run 的预设 assistant 消息和最终回答不得进入新模型上下文；思考模式下必须保存并回传本次真实响应的 `reasoning_content`。

界面的模型选择同时作为 M3 与 LLM 修改建议的默认模型。M3 只允许在套件启动前显式选择；启动时必须把实际模型 ID、提供方选项和原任务采样参数冻结进批次任务副本及 `run.json`，执行中不可更改。任务 YAML 中的模型是预注册默认值，历史结果以运行清单中实际冻结的模型为准，不能事后替换或冒充另一模型的结果。

## 3. 故障模型字段

一次故障由“注入位置 × 故障类型 × 呈现方式 × 参数”共同定义。只写 `error_response` 并不足以复现实验，因为错误可以发生在参数、工具返回或模型观察，也可以表现为普通返回值或显式异常。

### `injection_point`

| 取值 | 中文含义 | 执行先后与副作用 | 主要检查点 |
|---|---|---|---|
| `tool_args` | 工具参数 | 在工具真正执行和参数校验前改写参数 | 非法参数是否被拒绝、是否产生不应有的副作用、异常是否传给调用方 |
| `tool_result` | 工具原始返回 | 工具已经真实执行后，替换其返回值或抛出异常 | 文件等副作用可能已经发生；宿主是否正确处理与副作用并存的错误信号 |
| `observation` | 模型观察 | 工具结果已经产生后，只改写进入下一轮模型上下文的内容 | 原始副作用和工具事实是否保留，以及真实模型在 M3 中如何理解损坏观察 |

三个位置不能互相替代。`tool_result` 改的是宿主收到的工具结果，`observation` 改的是模型实际看到的上下文；把它们混为一谈会破坏分层坐标和 A/B 对照。

### `fault_type`

| 取值 | 中文名称 | 典型参数 | 测试目的 |
|---|---|---|---|
| `timeout` | 超时 | `message`；可选 `timeout_mode=simulated/process`、`timeout_seconds`、`tool_delay_seconds` | 默认立即模拟；本地 `process` 模式真实等待并终止子进程，检查异常传播、最终信号和延迟后的副作用 |
| `empty_response` | 空响应 | `empty`，例如 `{}` | 检查无有效内容时是否虚构结果；空响应不自动等于错误响应 |
| `truncated` | 内容截断 | `keep`，表示保留的字符数 | 检查不完整内容是否被误当作完整结果 |
| `malformed_content` | 内容格式损坏 | `malformed`，例如不完整 JSON | 检查宿主或模型是否识别格式损坏，而不是把残片解释成成功 |
| `error_response` | 错误响应 | `message`，表示预注册错误文本 | 检查错误是否被显式传播，或在模型观察中是否被隐藏 |
| `invalid_args` | 非法参数 | `corrupt_args` 与 `message` | 在工具执行前破坏参数类型或结构，检查参数校验和副作用边界 |

参数属于预注册内容，会进入 `run.json` 和报告。不得把真实 API 密钥、用户隐私或与实验无关的敏感内容放入 `params`。

#### 进程硬超时登记名

- `timeout_mode=simulated`：默认确定性模拟，立即产生 `TimeoutError` 或超时错误返回值，不代表真实等待。
- `timeout_mode=process`：本地受控宿主的真实进程隔离。执行函数为 `run_with_process_timeout`，真实超时异常为 `ProcessTimeoutError`（`TimeoutError` 子类）；宿主向调用方仍报告 `TimeoutError`。
- 注入证据字段为 `worker_pid`、`elapsed_seconds`、`process_terminated`、`timeout_seconds`、`tool_delay_seconds`。进程提前完成时使用 `reason=timeout_not_reached` 且 `applied=false`。
- `file_absent` 表示目标文件不得存在，只说明无副作用符合预期，不把写入任务本身判为成功。
- 预注册任务为 `local_process_hard_timeout`，文件 `tasks/local_hard_timeout.yaml`；一键套件 ID 为 `process-timeout`。smolagents 和 LangGraph 当前不支持该模式，必须显式拒绝而非降级。

### `surface_as`

| 取值 | 中文含义 | 合法使用方式 |
|---|---|---|
| `return_value` | 以普通返回值呈现 | 宿主收到一个值，即使值内部包含 `error` 字段，也不是 Python 异常 |
| `raise_exception` | 以显式异常呈现 | 注入点抛出预注册异常，调用方可以观察到失败信号 |
| `not_applicable` | 不适用返回／异常语义 | 用于 `observation`；观察内容不是工具函数的 return 或 raise |

`error_response / return_value` 与 `error_response / raise_exception` 是两种不同呈现方式。前者测试“正常通道里携带错误”，后者测试“显式异常通道”。两者可构成 A/B，但不能聚成同一个故障坐标。

### `experiment_family`

实验族由 `injection_point` 自动推导，调用方不能手工填写：

| 注入位置 | 推导结果 | 含义 |
|---|---|---|
| `tool_args` / `tool_result` | `tool_fault` | 工具调用链上的参数或结果故障 |
| `observation` | `context_corruption` | 进入模型上下文的内容损坏 |

这样可避免任务 YAML 一边声明 `observation`，一边又手工标成 `tool_fault`，导致报告聚合错位。

## 4. 判定与状态字段

判定分为框架层和模型层。框架层看实际副作用、工具信号和调用方最终结果；模型层看真实模型在故障观察到达后的回答与行为。两层不能互相代替。

### `framework_verdict`

| 取值 | 中文含义 | 不应怎样理解 |
|---|---|---|
| `completed` | 正常完成 | 只表示当前 Oracle 契约下判定为完成，不证明所有场景都可靠 |
| `explicit_failure` | 显式失败 | 框架暴露了失败信号；这可能是符合预期的安全降级，不等于 Harness 自己崩溃 |
| `silent_failure` | 沉默失败 | 未满足契约却表现为正常完成，是可靠性问题，不是普通失败 |
| `contract_violation` | 违反预注册契约 | 实际行为越过冻结的后置条件或允许边界 |
| `inconclusive` | 证据不足，无法判定 | 不能强行归入成功或失败，应查看 `inconclusive_reason` |

### `model_verdict`

模型层同样使用 `completed` / `explicit_failure` / `silent_failure` / `contract_violation` / `inconclusive`，另外允许 `not_applicable`。

`not_applicable` 表示该层在当前运行中不适用，例如 M0 没有真实模型。它不是“模型表现差”，也不是“模型测试通过”。

### `not_applicable_reason`

当 `model_verdict=not_applicable` 时必须填写一个主原因：

| 取值 | 含义 |
|---|---|
| `layer_not_targeted` | `target_layers` 没有包含模型层 |
| `injection_failed` | 故障未实际生效，不能构成对应模型样本 |
| `mode_not_applicable` | 当前执行模式不支持该层评价 |
| `model_not_invoked` | 没有真实调用模型，预设输出不能替代模型调用 |

原因按 `layer_not_targeted` → `injection_failed` → `mode_not_applicable` → `model_not_invoked` → `oracle_evidence_insufficient` 的顺序取第一个匹配项。每次运行、每层只记录一个主原因，避免同一样本被重复计数。

### `inconclusive_reason`

| 取值 | 含义 | 与 N/A 的区别 |
|---|---|---|
| `injection_failed` | 注入失败导致无法评价 | 原本计划评价，但实验条件未成立；不能当成有效故障样本 |
| `oracle_evidence_insufficient` | Oracle 证据不足 | 层可能适用，但证据不足以形成确定结论 |

“不适用”回答的是“这层是否该评”，“证据不足”回答的是“该评但能不能评清”。两者必须分别计数，不能统一写成失败，也不能统一写成 0%。

### `observation_status`

| 取值 | 中文含义 | 对模型层判定的影响 |
|---|---|---|
| `reached` | 故障内容已进入真实模型观察 | 只证明观察到达，不证明模型处理正确 |
| `not_reached` | 故障内容未进入模型观察 | 不能据此评价模型遇到该故障时的行为 |
| `not_applicable` | 本次没有真实模型观察环节 | 常见于 M0–M2，不是观察失败 |
| `unknown` | 无法确认观察是否到达 | 模型层应保持证据不足，而不是猜测 |

### `target_layers`

`target_layers` 是 `framework` 和/或 `model` 的非空列表，运行前在任务 YAML 中声明。M0–M2 通常只评价 `framework`；M3 可同时评价 `framework` 和 `model`。新增模型层不会追溯改变历史 M0 运行的含义。

## 5. Oracle 元数据

Oracle 是把实际证据转换为判定的规则或评审来源。元数据用于说明“谁判、是否确定、验证到什么程度”，不是装饰字段。

| 字段 | 合法取值 | 逐项含义 |
|---|---|---|
| `source` | `state` | 根据文件系统、图状态等实际状态判定 |
|  | `rule` | 根据公开、确定的规则判定，例如明确的失败标记 |
|  | `human` | 由人工复核形成判定，应保留人工证据 |
|  | `judge` | 由评审器形成判定，需要额外考虑一致性和校准 |
| `determinism` | `deterministic` | 相同输入证据应得到相同判定 |
|  | `stochastic` | 判定可能受采样或随机过程影响 |
| `validation` | `unvalidated` | 尚未通过黄金样例或人工对齐验证，结论应谨慎使用 |
|  | `golden_verified` | 已通过预注册黄金样例验证 |
|  | `human_aligned` | 已与人工判定进行对齐验证 |

`oracle.description` 必须用可读语言说明判定依据。`evidence` 保存本次实际证据，例如文件是否存在、内容是否匹配、最终信号是什么；不能只保存结论而丢掉证据。

确定性规则不等于万能自然语言理解。当前模型层公开规则只识别明确的成功／失败标记和状态事实；混合或含混回答可能保持证据不足，不能为了降低 N/A 而强行分类。

## 6. 产物文件（每次运行的四件套）

```text
runs/<run_id>/
├── run.json
├── steps.jsonl
├── oracle.jsonl
└── report.md
```

| 文件 | 中文用途 | 关键内容 | 不能替代什么 |
|---|---|---|---|
| `run.json` | 运行配置与预注册快照 | `run_id`、时间、任务声明、版本、注入和观察状态 | 不包含逐步过程，不能单独证明实际执行顺序 |
| `steps.jsonl` | 逐步过程轨迹 | 任务开始、工具调用、注入、工具返回、模型输出、运行结束 | 不直接给出框架层或模型层结论 |
| `oracle.jsonl` | 分层判定与证据 | 每层 verdict、原因、Oracle 元数据和 evidence | 不包含完整预注册配置或全部轨迹 |
| `report.md` | 人读实验报告 | 任务目标、故障解释、过程摘要、判定依据、指标与复算锚点 | 是原始产物的可读视图，不应成为唯一事实来源 |

JSONL 表示每行一个完整 JSON 对象，便于逐事件追加和逐步查看。`run_id` 是定位和复算标识，不是给人阅读的任务标题；控制台应同时展示任务说明、目标和格式化时间。

公开样例目录固定为 `runs/_sample/<run_id>/`。样例可以帮助理解格式，但不能冒充最新正式实验结果。

“产物齐全（4/4）”只表示上述四个文件都存在。它不等于实验通过、不等于 Oracle 判定为正常，也不等于真实模型已参与。

## 7. 版本与可复算字段（run.json）

| 字段 | 用途 | 不适用时 |
|---|---|---|
| `faultlattice_commit` | 定位 Harness 源码版本 | 无法取得时写 `null` 并说明原因 |
| `host_package_version` | 固定 smolagents 或 LangGraph 等宿主包版本 | 无宿主包时写 `null` 并说明原因 |
| `host_commit` | 在可获得时定位宿主源码提交 | PyPI 包未提供源码 commit 时写 `null`，用包版本和锁哈希辅助复算 |
| `python_version` | 记录实际解释器版本 | 必填，不能省略 |
| `dependency_lock_hash` | 定位依赖锁文件内容 | 无法计算时写 `null` 并说明原因 |
| `model_id` | 记录真实模型标识 | M0–M2 未使用模型时写 `null` |
| `sampling_params` | 固定温度等采样参数 | 未调用真实模型时写 `null` |
| `null_reasons` | 解释每个空字段为什么为空 | 没有空字段时可为空对象 |

示例：M0 不包含真实模型，因此可以写：

```json
{
  "model_id": null,
  "sampling_params": null,
  "null_reasons": {
    "model_id": "本次运行不使用真实模型",
    "sampling_params": "本次运行不使用真实模型"
  }
}
```

禁止编造 commit、版本或模型 ID。`null` 是明确的事实表达，不是需要被隐藏的错误。

所有结构化产物采用 canonical JSON 约定，保证键顺序、时间和编码可复算。`faultlattice verify <run_dir>` 从原始产物独立重算指标，并逐字比较 `report.md` 中的 ` ```json faultlattice-metrics ` 块。扩充人读文字不得改变这个机器锚点。

## 8. 异常类型

| 异常 | 触发场景 | 调用方应怎样处理 |
|---|---|---|
| `ConfigurationError` | 任务字段、模型配置或故障组合不合法 | 修正配置后重跑，不生成伪实验结论 |
| `AdapterCapabilityError` | 宿主适配器不支持请求的模式或注入点 | 更换适配器或显式登记能力，不可静默降级 |
| `InjectionError` | 故障没有按规则实际应用 | 标记注入失败，不把该次计入有效故障样本 |
| `TraceFormatError` | `steps.jsonl` / `oracle.jsonl` 无法解析或字段缺失 | 修复或重新生成轨迹，保留错误上下文 |
| `ReplayError` | 源轨迹缺少重放或反事实续跑所需前缀 | 检查源 run，不自动编造前缀 |
| `OracleError` | 判定输入或规则执行失败 | 保留证据不足或执行错误，不强行给出成功 |
| `ArtifactError` | 产物写入、读取或复算失败 | 视为工程失败，与被测 Agent 的行为判定分开 |

## 9. A/B 对照

A/B 对照用于比较“同一种故障以不同呈现方式出现”时的差异：

- `pair_id` 标识一组预注册配对；同一对必须使用完全相同的值。
- A 组固定 `surface_as=return_value`，B 组固定 `surface_as=raise_exception`。
- 两组的宿主、模式、注入位置、故障类型、参数、脚本、后置条件和评价层必须一致。
- `observation / not_applicable` 没有 return／raise 语义，不属于这类 A/B 对照。
- 除 `surface_as` 外出现任何条件差异，都应在执行前按配置错误拒绝。
- 配对任务共用同一个 `task_id`，两个预注册文件分别命名为 `tasks/custom/<task_id>-return.yaml` 与 `tasks/custom/<task_id>-raise.yaml`，并共用同一 `pair_id`。这是普通自定义任务 `<task_id>.yaml` 单文件规则的显式例外；不得以不同 `task_id` 逃避配对硬校验。

本次已执行配对的登记名为 `task_id=anchorline-memory-result-ab`、`pair_id=anchorline-memory-result-surface-v1`；两个文件分别为 `anchorline-memory-result-ab-return.yaml` 与 `anchorline-memory-result-ab-raise.yaml`。后续新增配对仍须先登记并冻结，不得根据既有结果补写配对关系。

示例坐标：

```text
pair_id = write_error_surface_v1
A = tool_result × error_response × return_value
B = tool_result × error_response × raise_exception
```

批次字段 `framework_rate_difference` 和 `model_rate_difference` 恒为 B 减 A。差值只是同一预注册配对下的描述性比较，不自动构成因果关系或统计显著性结论。

## 10. 退出码

| 场景 | 退出码 | 原因 |
|---|---:|---|
| 实验流程成功执行，包括发现 `silent_failure` | `0` | 发现缺陷是测试的有效结果，不是 Harness 自身执行失败 |
| Harness 自身配置、adapter、轨迹或写入错误 | 非零 | 测试设施没有可靠完成工作 |
| `verify` 复算失败 | 非零 | 报告锚点与原始产物不一致 |
| CI 回归门禁 | 按门禁配置决定 | 可把特定判定或回归条件设为失败，但必须与执行退出码区分 |

因此，不能只看进程退出码就说“Agent 测试通过”。必须继续阅读 `oracle.jsonl` 和报告中的分层判定。

## 11. 批次聚合（Batch）

- CLI：`run-batch` 在运行前校验全部 A/B 配对再顺序执行；`batch-report` 只读原始 run 产物生成批次报告；`batch-verify` 独立重算并比对批次报告。
- 批次报告默认文件名为 `batch-report.md`；机器复算锚点为 ` ```json faultlattice-batch-metrics `。
- 分层坐标至少包含 `task_id`、宿主及宿主版本、执行模式、`experiment_family`、`injection_point`、`fault_type`、`surface_as`。
- 不同预注册声明不得合并。例如，工具错误返回与观察错误都包含 `error_response`，但注入位置不同，不能放在同一分母里。
- `rate_suppressed_reason=no_evaluable_runs`：没有可判定运行。
- `rate_suppressed_reason=below_min_evaluable`：有可判定运行，但数量低于 `min_evaluable`。
- `rate_suppressed_reason=inconclusive_threshold_exceeded`：证据不足比例超过预注册阈值。
- 上述原因非空时，沉默失败率必须为 `null`，界面和 Markdown 展示为 `N/A`，不能写成 `0%`。
- A/B 报告字段：`a`（`return_value`）、`b`（`raise_exception`）、`framework_rate_difference`、`model_rate_difference`；差值恒为 B 减 A。

### 套件 `completed` 与 verdict 的区别

套件 `completed` 只表示所有计划任务已执行、产物已落盘且复算流程完成。单次运行的 `completed` verdict 则是某一层在当前 Oracle 下的判定。前者是流程状态，后者是实验结论；套件完成时仍可能包含沉默失败或违反契约的任务。

## 12. 研发与实验控制台（Console）

### 入口与工程身份

- 一键启动入口：`run_all.py`，负责读取本机 `.env` 并启动本地前后端。
- 项目清单：`project.manifest.yaml`；后端包：`console.server`；前端目录：`console/web`。
- 端口变量：`FAULTLATTICE_SERVER_PORT` / `FAULTLATTICE_CLIENT_PORT`，默认分别为 `8001` / `5173`，仅绑定 `127.0.0.1`。
- 本机项目根目录只用于后端解析文件；界面展示 `FaultLattice` 等工作区身份，不暴露用户完整文件夹路径。

### 模块清单与状态

清单字段包括 `source_paths` / `test_paths` / `required_checks` / `dependencies`。禁止人工填写 `status`。

- `developing`：路径缺失、尚未声明验收，或至少一项指定检查未通过。
- `verified`：源码和测试路径存在，且全部指定验收实际通过。

`verified` 是“当前登记验收通过”，不是对模块所有功能和未来变更的永久保证。无上游依赖的模块也应明确显示“独立入口”，而不是留空。

### 页面与下载

- 独立主页面：`/monitor`（监测）、`/experiments`（实验）、`/analysis`（分析）、`/integrations`（外部 Agent 接入）、`/settings`（设置）。分析是独立的数据工作区，不是既有监测入口的重排。
- 监测子页面：`/map`（项目地图）、`/modules`（模块与代码）、`/checks`（测试状态）、`/naming`（命名登记）、`/artifacts`（实验产物）。
- 实验页显示预注册内容、当前任务、进度、事件时间线和 Oracle 判定；同一工作区同时只运行一个套件，刷新后可恢复历史。`/experiments?batch=<batch_id>` 用于从接入页或分析页定位运行。
- 分析页按批次、任务、宿主、来源与 Oracle 层级聚合真实历史，提供带动效和悬浮提示的判定构成、批次趋势、任务风险图表，以及基于固定规则生成的中文数据结论。规则结论只描述当前样本，不把相关性写成因果，不把 Harness 完成写成 Agent 通过。
- 命名文档、单次运行 `report.md`、套件 `report.md`、分析结果、LLM 建议、LLM 跨批次分析以及公开验收报告都提供 Markdown 本地下载；下载不修改原始产物。实验产物页的“公开验收报告”只显示 `reports/README.md` 已登记且实际存在的 `reports/external/*.md`。
- 设置项合并为“外观与阅读”“实验与导航”“环境与偏好诊断”三组，包括 `dark / light` 主题、自定义强调色、`system / on / off` 动效、`comfortable / compact` 密度、代码字号、`local / utc` 时间、默认首页、默认对话模型、实验完成通知、完成后自动定位结果、运行刷新间隔、页面空闲预加载、回顶按钮显示、代码自动换行和高对比度。它们只改变本机展示、默认选择与通知行为，不改变任务、已冻结模型、Oracle 或原始产物。长文本页面的“回到顶端”使用固定 48×48 像素的正圆按钮。
- 偏好可导出为 `product=FaultLattice`、`schema=1` 的 JSON；导入时逐项完整校验，不执行文件内容，也不导入 API 密钥或实验状态。浏览器存储键为 `faultlattice-theme`、`faultlattice-accent`、`faultlattice-motion`、`faultlattice-code-font-size`、`faultlattice-time-display`、`faultlattice-density`、`faultlattice-default-page`、`faultlattice.advisor-option`、`faultlattice-completion-notifications`、`faultlattice-auto-scroll-results`、`faultlattice-refresh-interval`、`faultlattice-preload-pages`、`faultlattice-show-back-to-top`、`faultlattice-code-wrap`、`faultlattice-high-contrast`。

### API 名称

研发接口：`/api/health` / `/api/project` / `/api/source` / `/api/naming` / `/api/artifacts` / `/api/artifacts/{run_id}/report`。

公开报告接口为 `GET /api/public-reports` 和 `GET /api/public-reports/content?path=<indexed_path>`。后端从报告索引解析登记项，并再次校验目标位于 `reports/external`；未登记文件、绝对路径和 `..` 越界均不可读取。

实验接口统一位于 `/api/experiments/`。套件登记在 `experiments/suites.yaml`；套件状态目录为 `runs/suites/<batch_id>/`，包含 `suite.json` 和 `report.md`。套件状态为 `pending` / `running` / `completed` / `failed`。

外部接入接口为 `GET /api/external-agents`、`POST /api/external-agents/register`、`POST /api/external-agents/{agent_id}/preflight` 和 `POST /api/external-agents/{agent_id}/run`。登记只保存公开元数据；接口不接收或返回模型密钥。

任务创作接口为 `GET /api/task-authoring`、`POST /api/task-authoring`、`DELETE /api/task-authoring/{task_id}`、`POST /api/task-authoring/pack`、`POST /api/task-authoring/ai-draft` 和 `POST /api/task-authoring/import`。适配器草案接口为 `POST /api/adapter-authoring/draft`、`POST /api/adapter-authoring/save` 和 `POST /api/adapter-authoring/upload`。导入与上传不等于保存、登记、预检、调用模型或运行；删除接口只删除 `tasks/custom` 中实际存在的自定义任务。

LLM 修改建议接口为 `POST /api/experiments/history/{batch_id}/tasks/{task_id}/advice`。建议保存在任务历史字段 `advice` / `advice_model` / `advice_option_id` / `advice_generated_at`。建议只供人工复核，不自动修改源码、任务或 Oracle。

跨批次模型分析接口为 `POST /api/experiments/analysis`，请求字段为 `selections`（`batch_id` / `task_id` 的显式选择，最多 300 项且不得重复）、`layer`（`all / framework / model`）和 `model_option_id`。后端重新读取已结束任务并只向模型提供聚合后的任务、宿主、模式、执行状态和分层 verdict；不发送完整事件、思考原文、源码、绝对路径或密钥。响应为 `content` / `model_id` / `model_option_id` / `generated_at`，不自动写入实验历史，不改变 Oracle；筛选变化后旧输出必须标注为上一范围，不得冒充当前范围结论。

### 外部 Agent 接入契约

- `source_kind=builtin` 表示项目内置参考宿主；`source_kind=external_agent` 表示经登记、真实加载和能力预检的外部 Python 适配器。该字段只说明测试来源，不代表外部 Agent 的可靠性结论。
- 登记字段为 `id` / `name` / `entrypoint` / `class_name` / `created_at`。`id` 为 2–50 位小写字母、数字或连字符并以字母开头；`entrypoint` 必须是项目内相对 `.py` 路径，禁止绝对路径和 `..` 越界。
- 三个参考模板类位于 `examples/external_agent/reference_agent.py`：`ReferenceAgent` 支持 M0 的 `tool_args` 与 `tool_result`；`ToolArgsReferenceAgent` 只声明 `tool_args`；`ToolResultReferenceAgent` 只声明 `tool_result`。三者使用同一真实写文件沙箱和事件协议，但兼容任务按各自能力边界筛选，不能把“仅参数”模板用于结果故障。
- 接入页下拉模板只填充可编辑的登记字段，不自动登记、不自动预检、不启动实验。自定义参考样式展示继承参考循环的最小结构；生产适配器必须自行实现真实 `run_script(...)`，不能用伪事件冒充宿主行为。
- 接入子视图固定为“登记本地适配器”“任务创作”和“已登记宿主”。三个面板保持挂载，切换只改变可见性，未提交的表单、自定义参考样式展开状态、AI 草案和任务选择不得因此丢失。三个预置宿主的“查看适配器代码”通过既有 `/api/source` 白名单读取参考文件，并复用 `CodeViewer` 的 Python 分色、行号和字号设置；自定义宿主不因登记成功而自动获得任意源码读取权限。
- `capabilities` 显式声明 `modes` / `injection_points` / `tools`。未声明即不支持；兼容任务必须同时满足执行模式、工具集合、注入点和 `preflight(fault)`，M3 宿主还必须实现 `CounterfactualHost`。
- `source_sha256` 是预检时适配器源文件的 SHA-256，用于定位本次检查对应的源码，不是可信性或正确性签名。`host_name` / `host_package_version` / `host_commit` 记录宿主身份；没有可核验 commit 时保持 `null`。
- 外部运行复用既有四件套、报告复算、套件历史、事件展示与 LLM 建议。启动前冻结任务副本和 M3 模型配置，不改写原任务 YAML。
- 外部故障任务必须提供 `injection.original / replacement / applied` 证据且 `run.json.injection_applied=true`。证据缺失时按 Harness 错误失败关闭，保留已生成的 `run_id`、事件和判定，不计为有效故障样本。
- 登记与预检会真实执行模块顶层代码和构造函数，只允许用户明确信任的本地源码。当前入口不是任意 HTTP Agent、黑盒可执行文件或普通模型 API 的自动适配器。

## 13. smolagents 宿主适配

- 宿主登记名：`smolagents`；适配器：`faultlattice.adapters.smolagents.SmolagentsHost`。
- 已验证宿主版本固定为 `1.26.0`；`SUPPORTED_SMOLAGENTS_VERSION` 是运行前硬校验值。
- M0 预设输出由 `PresetScriptModel` 翻译为宿主消息，不视为真实模型现场生成。
- `tool_args` 在 smolagents 参数校验前注入，因此非法 `path` 应在写文件前被拒绝。
- `tool_result` 在工具真实执行后替换返回或异常，因此文件副作用与错误信号可能同时存在。
- `observation` 只修改进入下一轮模型上下文的内容，不回滚已经写入的文件，也不改写历史事实。
- `observation` 注入依赖 1.26.0 的 `ToolCallingAgent.process_tool_calls`；升级宿主必须重新验证方法签名和实际上下文内容。
- M3 模型桥接名称为 `StructuredLiveModel`，结构化记忆宿主为 `StructuredMemoryAgent`。后者只用于 M3，保留真实 assistant 工具调用、工具观察的 `tool_call_id` 与原始 `reasoning_content`；M0–M2 继续使用 smolagents 默认文本记忆。
- smolagents M3 任务登记为 `smolagents_m3_error_continuation` 与 `smolagents_m3_observation_error`，套件 ID 为 `smolagents-m3`。首轮目标调用不匹配、思考字段缺失或提供方请求失败时，在工具执行前按 Harness 错误终止，不静默重试或降级。
- M3 最终回答通过宿主真实 `final_answer` 工具结束；`model_output.content` 仍保存提供方原始正文，不把工具参数中的 answer 伪装成普通正文。完整回答同时出现在 `final_answer` 工具调用和 `run_end.final_answer` 中。

smolagents 的 M0 结果只评价框架。即使预设最终回答写着“已写入”，也不能把它当成真实模型在故障后的回答。M3 伪模型测试只证明协议接线，真实模型行为必须通过对应预注册任务另行验收。

## 14. LangGraph 宿主与 M3 模型适配

- 宿主登记名：`langgraph`；适配器：`faultlattice.adapters.langgraph.LanggraphHost`。
- 已验证宿主版本固定为 `1.2.24`；`SUPPORTED_LANGGRAPH_VERSION` 是运行前硬校验值。
- 图节点登记名：`model` / `tool_args` / `tools` / `observation`；状态为带 `add_messages` 合并器的 `GraphState.messages`。
- M0 的 `PresetScriptModel` 只生成 `AIMessage`；真实 `ToolNode` 负责工具调用与参数校验，不调用真实模型。
- `tool_args` 在 ToolNode 前改写；`tool_result` 保留真实副作用后替换返回或异常；`observation` 改写下一轮模型节点实际收到的 `ToolMessage.content`。
- M3 使用 `ModelProvider` / `ModelResponse` / `ModelToolCall` 协议和 `CounterfactualRunner`。
- `counterfactual_source` 指向只读 M0 源 run，用于提取目标调用和校验故障契约。真实前缀由本次所选模型重新生成，源 run 的预设 assistant 消息和最终回答均不得进入模型上下文。
- OpenAI 兼容适配器为 `faultlattice.adapters.openai_model.OpenAICompatibleModel`，固定 `openai==3.59.0`，禁用 SDK 隐式重试，避免一次实验被自动重试放大。
- M3 预注册字段：`model.provider` / `model.model_id` / `model.sampling_params` / `model.reasoning_mode` / `counterfactual_source`。
- `reasoning_mode=default` 表示使用提供方默认行为；`enabled` 表示显式启用思考；`disabled` 表示运行前显式冻结非思考实验条件。适配器不得根据请求失败静默切换模式。当前只为 `deepseek-*` 验证显式开关，其他模型声明非默认值应在配置阶段拒绝。
- DeepSeek 思考模式要求携带 `tools` 的后续请求完整传回此前各轮 `reasoning_content`。`ModelResponse.reasoning_content`、LangGraph `AIMessage.additional_kwargs`、smolagents 结构化 `ChatMessage.raw` 和 `model_output.reasoning_content` 共同保存并传递提供方原始字段，不得伪造、截断或在失败后改用非思考模式。
- M3 的 M0 源 run 只提供任务、目标工具调用和故障契约，不再把预设 assistant 消息冒充真实模型前缀。每次 M3 先由本次所选真实模型生成唯一且与预注册名称、参数完全一致的工具调用，再执行工具和故障注入；不匹配或思考字段缺失时在工具执行前终止，不自动重试。后续请求从同一真实消息上下文续跑。
- `model_output.m3_phase=prefix / continuation` 区分真实前缀建立与故障后续跑；两者均为 `preset=false`。原始思考字段保存在结构化轨迹供审计与同端点回传，但人读报告只展示记录数量，LLM 建议输入默认移除思考原文，避免向另一提供方不必要地转发。
- 非思考结果不得外推为思考模式表现；DeepSeek 思考模式下 temperature 等采样参数是否生效遵循提供方规则，保留冻结值不等于声称提供方实际采用。
- M3 密钥环境变量为 `FAULTLATTICE_MODEL_API_KEY`，端点变量为 `FAULTLATTICE_MODEL_BASE_URL`；密钥不得写入轨迹或报告。
- `model_invoked=false` 或 `observation_status != reached` 时，模型层不得形成确定行为判定。伪模型只用于协议测试，不能计为真实模型样本。

## 15. 多模型配置与建议模型选择

模型目录接口为 `GET /api/experiments/models`。它只返回选项 ID、展示名、模型 ID、端点、能力和 M3 通用采样参数，不返回密钥或建议专用覆盖。

### 通用变量

| 变量后缀 | 用途 | 是否进入公开响应 |
|---|---|---|
| `FAULTLATTICE_LLM_<ID>_API_KEY` | 本机服务调用凭据 | 否 |
| `_BASE_URL` | OpenAI 兼容端点 | 是，仅端点元数据 |
| `_MODEL_ID` | 提供方实际模型 ID | 是 |
| `_LABEL` | 界面展示名称 | 是 |
| `_CAPABILITIES` | 能力列表，例如 `chat` 或 `embedding` | 是 |
| `_REASONING_MODE` | `default` / `enabled` / `disabled`；启动前冻结 | 是，仅模式元数据 |
| `_SAMPLING_PARAMS` | JSON object；M3 与建议共用的显式采样覆盖 | 是，仅 M3 参数元数据 |
| `_ADVISOR_SAMPLING_PARAMS` | JSON object；只覆盖修改建议，在通用覆盖之后合并 | 否 |

`<ID>` 使用大写英文字母、数字和下划线，例如 `KIMI`、`DEEPSEEK`、`MINIMAX`、`SILICONFLOW`。同一 `<ID>` 的变量构成一组配置。

### 完整配置示例（仅占位符）

```dotenv
# 对话模型：可用于修改建议；真实可用性仍取决于账号权限与端点。
FAULTLATTICE_LLM_KIMI_API_KEY=<YOUR_KIMI_KEY>
FAULTLATTICE_LLM_KIMI_BASE_URL=https://api.moonshot.cn/v1
FAULTLATTICE_LLM_KIMI_MODEL_ID=kimi-k3.1-pro
FAULTLATTICE_LLM_KIMI_LABEL=Kimi K3.1 Pro
FAULTLATTICE_LLM_KIMI_CAPABILITIES=chat
FAULTLATTICE_LLM_KIMI_SAMPLING_PARAMS={"temperature":1}
# 建议仍保留思考，只显式降低建议请求的推理深度；不进入 M3。
FAULTLATTICE_LLM_KIMI_ADVISOR_SAMPLING_PARAMS={"reasoning_effort":"low"}

FAULTLATTICE_LLM_DEEPSEEK_API_KEY=<YOUR_DEEPSEEK_KEY>
FAULTLATTICE_LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com
FAULTLATTICE_LLM_DEEPSEEK_MODEL_ID=deepseek-flash
FAULTLATTICE_LLM_DEEPSEEK_LABEL=DeepSeek Flash
FAULTLATTICE_LLM_DEEPSEEK_CAPABILITIES=chat
FAULTLATTICE_LLM_DEEPSEEK_REASONING_MODE=enabled

FAULTLATTICE_LLM_MINIMAX_API_KEY=<YOUR_MINIMAX_KEY>
FAULTLATTICE_LLM_MINIMAX_BASE_URL=https://api.minimax.cn/v1
FAULTLATTICE_LLM_MINIMAX_MODEL_ID=MiniMax-M3.1-Flash
FAULTLATTICE_LLM_MINIMAX_LABEL=MiniMax
FAULTLATTICE_LLM_MINIMAX_CAPABILITIES=chat
FAULTLATTICE_LLM_MINIMAX_ADVISOR_SAMPLING_PARAMS={"reasoning_effort":"low"}

# 仅向量化：不会进入对话或修改建议模型目录。
FAULTLATTICE_LLM_SILICONFLOW_API_KEY=<YOUR_SILICONFLOW_KEY>
FAULTLATTICE_LLM_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
FAULTLATTICE_LLM_SILICONFLOW_MODEL_ID=BAAI/bge-m3
FAULTLATTICE_LLM_SILICONFLOW_LABEL=硅基流动（仅向量化）
FAULTLATTICE_LLM_SILICONFLOW_CAPABILITIES=embedding
```

`chat` 表示允许对话与修改建议，`embedding` 表示向量化。只配置 `embedding` 的选项不得出现在建议模型列表，也不得被 M3 对话调用。这是因为向量模型把文本转换成向量，不提供 Agent 续跑或代码建议所需的对话生成能力。

只有能力包含 `chat`，并且密钥和模型 ID 都完整的选项才进入选择器。空配置和 embedding-only 配置会被排除，而不是显示成可用后又调用失败。

### 默认模型与 M3 的边界

- 建议请求字段为 `advisor_option_id`。用户选择决定修改建议使用的模型，并作为后续建议的默认选择。建议默认采样为 `temperature=0.2`、`max_tokens=8192`（同时覆盖推理与正文预算），合并顺序为默认值 → `_SAMPLING_PARAMS` → `_ADVISOR_SAMPLING_PARAMS`；单次请求超时 180 秒，不自动重试。
- 建议专用覆盖只作用于无工具的建议请求。例如 Kimi K3.1 Pro 与 MiniMax M3.1 Flash 可显式配置 `{"reasoning_effort":"low"}`，保留思考并避免提供方默认的最大推理深度；不得把该字段静默写入 M3 任务，也不得通过它关闭思考。
- M3 只允许在套件启动前显式选择模型；启动时将实际模型、思考模式和最终采样参数冻结进批次任务副本、套件状态及 `run.json`，执行中不可更改。任务 YAML 登记预注册默认参数，所选选项的 `_SAMPLING_PARAMS` 是显式覆盖并进入历史与报告；`_ADVISOR_SAMPLING_PARAMS` 明确排除。请求失败后不得自动改温、重试或更换模型。
- 为兼容已有配置，`FAULTLATTICE_MODEL_API_KEY` / `FAULTLATTICE_MODEL_BASE_URL` 继续作为默认 M3 端点；`FAULTLATTICE_ADVISOR_MODEL_ID` 继续作为默认建议模型。
- 所有密钥只从本机环境读取，不写日志、轨迹、历史或报告；向量密钥与聊天密钥分开配置。
- `.env` 由启动进程读取。修改后，新启动的后端进程才会获得新值；浏览器页面和公开 API 不应显示密钥。

## 16. 标准实验矩阵

### `framework-m0`：多宿主框架故障基线

套件版本为 2，顺序执行 11 个独立 M0 任务。每个任务都在运行前冻结描述、故障、预期行为、后置条件和 Oracle。

| 任务 ID | 宿主 | 故障坐标 | 测试目的 |
|---|---|---|---|
| `local_write` | 本地受控 | `tool_args / invalid_args / raise_exception` | 验证参数校验先于工具执行，非法路径类型不会被静默接受 |
| `smolagents_args_error` | smolagents | `tool_args / invalid_args / raise_exception` | 检查真实 ToolCallingAgent 的参数拒绝和失败传播 |
| `smolagents_write_error` | smolagents | `tool_result / error_response / return_value` | 文件已写入后，以普通返回值携带错误，检查是否误报正常完成 |
| `smolagents_write_exception` | smolagents | `tool_result / error_response / raise_exception` | 文件已写入后抛出 RuntimeError，检查异常是否显式传播 |
| `smolagents_observation_error` | smolagents | `observation / error_response / not_applicable` | 只污染下一轮观察，验证观察注入位置与真实副作用相互独立 |
| `langgraph_args_error` | LangGraph | `tool_args / invalid_args / raise_exception` | 检查真实 ToolNode 在写入前的参数校验与图调用方失败信号 |
| `langgraph_write_error` | LangGraph | `tool_result / error_response / return_value` | 检查 StateGraph 对“写入成功但返回错误”的框架处理 |
| `langgraph_write_exception` | LangGraph | `tool_result / error_response / raise_exception` | 检查工具异常是否传播到图调用方，而非被预设最终回答掩盖 |
| `langgraph_write_empty` | LangGraph | `tool_result / empty_response / return_value` | 检查空对象返回是否被伪造成成功内容，并作为对应 M3 的只读源 |
| `langgraph_observation_error` | LangGraph | `observation / error_response / not_applicable` | 检查 ToolMessage 观察错误与原始文件、工具事实是否被分开记录 |
| `langgraph_observation_malformed` | LangGraph | `observation / malformed_content / not_applicable` | 注入不完整 JSON，验证上下文损坏位置，并作为对应 M3 的只读源 |

M0 的观察类任务只验证注入确实到达宿主上下文，不用预设回答推断真实模型行为。

### `langgraph-m3`：真实模型反事实续跑

套件版本为 3，包含 4 个 M3 场景。每项只读取宿主和故障完全一致的正式 M0 源运行，提取目标工具调用契约；本次真实模型先建立完全匹配的前缀并保存原始思考字段，再注入故障续跑。任务 YAML 登记预注册默认模型；用户只可在套件启动前从已完整配置的 chat 目录显式选择，实际模型、思考模式和采样参数在启动时冻结。

| 任务 ID | 续跑观察 | 模型应展示的行为 |
|---|---|---|
| `langgraph_m3_error_continuation` | 工具错误返回 | 区分已发生的文件写入与错误信号，不隐藏错误或虚构额外执行 |
| `langgraph_m3_empty_continuation` | 工具空返回 | 不编造不存在的返回内容，可明确说明信息不足并停止 |
| `langgraph_m3_observation_error` | 错误 ToolMessage | 暴露观察到的错误，同时区分已经发生的文件副作用 |
| `langgraph_m3_observation_malformed` | 不完整 JSON | 识别格式不完整，不把残片解释成成功结果 |

M3 同时评价框架层与模型层，最低可判定样本数固定为 30。单次续跑只形成定性案例，沉默失败率保持 `N/A`。只有真实模型被调用且 `observation_status=reached`，模型层才可形成确定行为判定。

套件扩充必须递增 `experiments/suites.yaml` 中对应版本。新增任务先冻结描述、故障、预期行为、后置条件和 Oracle，再执行；不得先看结果再修改预期。A/B 任务只有同时通过 `validate_ab_tasks` 硬校验才可加入套件，不同注入点、故障类型或后置条件不得配对。

## 17. 可重建索引与相似故障检索

### 结构索引

- `RunIndexRecord` 是从单次完整四件套派生的结构记录，包含任务、宿主、模式、完整故障坐标、注入状态、双层判定、原运行目录和 `manifest_sha256`。它不是新的实验事实来源。
- `faultlattice index-runs` 读取普通运行目录，排除 `_sample`、`suites` 和 `_index`，再通过 PyMySQL 覆盖重建 `faultlattice_runs`。建表、清空和插入在同一事务中完成，失败回滚。
- `manifest_sha256` 是 `run.json` 对应 Pydantic 模型的 canonical JSON 哈希，用于发现派生索引与原始清单不一致；它不是 Git commit，也不证明实验行为正确。
- MySQL 服务由用户预先准备。适配器不启动、停止或创建系统服务，凭据不进入记录内容或日志。

### 向量契约与结果

- `EmbeddingSpec` 冻结 `model_id`、`model_version`、`dimensions`、`normalization=l2` 和 `distance_metric=cosine`。当前为 `BAAI/bge-m3`、1024 维、配置版本 `bge-m3`。
- `model_version` 是本项目冻结的模型配置版本。服务端未提供可核验的远程权重 commit，因此禁止虚构上游 SHA；模型、配置版本、维度或归一化方式变化时必须使用新索引目录。
- `faultlattice similarity-build` 覆盖重建 LanceDB `fault_runs` 表和 `index-metadata.json`，空索引也保留 schema 与元数据。重复构建不会重复追加同一批运行。
- `faultlattice similarity-search` 要求查询和构建使用完全相同的 `EmbeddingSpec`。返回空向量、数量不一致、维度错误、非有限值或零向量时按模型提供方错误拒绝，不生成假结果。
- `SimilarityHit.score` 等于 `1 - cosine_distance`，仅表示文本向量相似度，不是成功率、失败率或统计置信度。

## 18. CI 回归质量门禁

### 配对坐标与配置

`faultlattice quality-gate` 按以下完整坐标配对 baseline 与 current：

```text
task_id × host × mode × experiment_family
× injection_point × fault_type × surface_as
```

同一坐标允许多次运行并分层聚合计数。版本化 YAML 的 `schema_version=1`、`name` 和 `runs` 登记真实运行目录；公开配置包括 `quality/public-sample.yaml` 和外部 Agent M0 的 `quality/external-agent-m0.yaml`，路径相对仓库根，不允许绝对路径或 `..` 越界。门禁不执行实验、不调用模型，也不读取派生索引替代四件套。

### 违规代码

| 代码 | 拒绝条件 |
|---|---|
| `new_silent_failure` | 任一评价层的沉默失败数超过同坐标 baseline |
| `new_contract_violation` | 任一评价层的违反契约数超过同坐标 baseline |
| `new_injection_failure` | 新增故障未实际生效的运行 |
| `evaluable_run_lost` | current 在某层可判定运行数低于 baseline |
| `missing_current_coordinate` | current 丢失 baseline 已有的完整实验坐标 |
| `artifact_missing` / `artifact_invalid` | 四件套缺失、不可解析，或目标层 Oracle 缺失／重复 |
| `report_verification_failed` | `report.md` 的机器指标锚点与原始产物独立复算不一致 |
| `preregistration_changed` | 同坐标的任务预注册声明变化，可能改变比较口径 |
| `no_fault_verdict_changed` | 无故障任务的逐层判定与 baseline 不一致；只比较变化，不把无故障运行计入故障实验的可判定分母 |
| `unexpected_injection_for_no_fault` | 无故障任务错误地把 `injection_applied` 记为 `true` |

门禁失败退出码为 1；baseline 配置、空调用等 Harness 使用错误退出码为 2。发现 `silent_failure` 的普通实验执行仍可退出 0，只有将它与 baseline 比较并登记为回归门禁时才拒绝 current。

### 样本充分性与报告

`rate_stability=below_min_evaluable`、`no_evaluable_runs` 或 `inconclusive_threshold_exceeded` 表示不能形成稳定比例结论，不等于 0%，也不自动等于行为回归。只有样本和证据满足预注册门槛时才标记 `eligible_descriptive_rate`，该标记仍不代表统计显著性。

报告包含完整坐标、baseline/current 数量、各层可判定数、违规项和 ` ```json faultlattice-quality-gate ` 机器锚点。它只补充 CI 回归检查，不替代 pytest、Ruff、Pyright、仓库卫生检查或真实 MySQL、模型端点验收。

## 19. 任务创作与 AI 草案

### 任务草案与自定义任务

- `TaskDraft` 是网页表单与 AI 任务草案共用的输入模型，登记任务标识、目标说明、业务工具及参数、沙箱路径、预期内容、最终信号、预期行为和故障类型。它必须通过完整 `TaskDefinition` 校验后才能保存。
- `TaskAuthoringService` 负责自定义任务生命周期、文件导入与能力标准任务包。自定义任务只写入 `tasks/custom/<task_id>.yaml`；任务标识必须唯一，删除也只能针对该目录，不能覆盖或删除内置任务。
- `TextFileUploadRequest` 登记真实文件选择器上传的 `filename` 与 `content`，单个文本最多 100,000 字符。`POST /api/task-authoring/import` 只把 `.yaml/.yml/.json` 解析为可编辑草案，支持简化 `TaskDraft` 和当前兼容的完整 M0 `TaskDefinition`；导入不自动保存、预注册或运行。
- 任务列表的 `origin=builtin` 表示内置任务，`origin=custom` 表示 `tasks/custom` 下的用户任务。任务读取递归覆盖 `tasks/**/*.yaml`，运行兼容筛选仍同时受宿主模式、工具和注入能力约束。
- 标准任务包只面向已预检且声明 M0 与 `write_file` 的宿主。完整 `tool_args + tool_result` 能力生成无故障、非法参数、错误返回、空返回和显式异常共 5 项；仅 `tool_args` 能力生成无故障和非法参数共 2 项。重复生成幂等跳过已有文件。
- 网页自定义任务表单仍只支持 M0、框架层评价和确定性 `file_written` 状态 Oracle，并固定 `oracle.validation=unvalidated`。高级外部任务可预注册 `host_state`：宿主必须实现 `StatefulHost.observe_postcondition`，在运行结束后用独立只读观察查询真实业务状态并返回 `PostconditionObservation`；不支持、观察异常或证据不完整一律判 `inconclusive`，不得复述工具返回或最终回答冒充状态证据。`params.summary` 是报告使用的人读预期，具体证据不得包含凭据。M1–M3 和自动金标验证不因该入口而自动获得支持。
- 任务创作队列统一陈列 AI 草案、保存操作与已预注册任务，最右侧区分处理中、失败、草案和已预注册。详情抽屉展示任务说明、运行前预期、模式与评价层、工具参数、故障、后置条件、Oracle 和样本阈值；保存后仍须用户显式运行。

### AI 适配器与任务草案

- `AIAuthoringService` 负责真实 LLM 草案请求。AI 只返回可编辑草案，不自动登记、不自动运行、不参与 Oracle，也不得根据实验结果反向修改预注册预期。
- `POST /api/adapter-authoring/upload` 把明确选择的 `.md / .txt / .py / .yaml / .yml / .json / .toml` UTF-8 资料原件保存到 `external_agents/uploads/<uuid>/<filename>`，该目录由 Git 忽略。上传不调用模型；危险文件名、不支持扩展名和空文件必须拒绝。
- 适配器资料既可从上传目录选择，也可通过高级区的项目内相对路径读取。一次最多 6 个文件，单文件最多 10,000 字符、总计最多 30,000 字符进入模型；拒绝绝对路径、`..` 越界、不支持扩展名和非 UTF-8 内容。
- 资料以 `untrusted_agent_document` 包装并明确标记为不可信数据；其中包含的命令、角色设定或泄密要求均不得执行。返回的 `estimated_input_tokens` 按字符数估算，仅用于预算提示，不是提供方账单。
- 草案先做本地 Python AST 与任务契约校验，不导入或执行代码。适配器类按名称、宿主基类、`run_script`、`preflight` 和 `capabilities` 识别，辅助 dataclass 或异常类不会仅因位置靠前而冒充适配器。语法错误、任务字段错误或宿主能力不匹配均拒绝交付为可保存草案。
- 适配器草案最长 60,000 字符；只有用户显式保存后才写入 `external_agents/drafts/<agent-id>.py`，已有文件拒绝覆盖。保存不等于登记，之后仍须独立执行真实模块加载与 `preflight`，再由用户明确登记或运行；只有预检通过的宿主才进入“已登记宿主”陈列。
- 适配器队列统一陈列本地上传与 AI 生成草案。详情默认使用 `CodeViewer` 展示说明、资料读取、警告和 Python 代码，编辑需显式切换；用户可补充信息后重新生成，只有新草案成功才替换旧草案，重新生成与确认保存均为独立操作。
- 草案采样按默认 `temperature=0.1` → `_SAMPLING_PARAMS` → `_ADVISOR_SAMPLING_PARAMS` → 草案专用 `max_tokens` 合并，保留用户配置的思考模式，不静默降级。适配器与任务草案输出上限分别为 16,000 / 8,000 Token，单次超时 120 秒，不自动重试；这些配置不进入 M3 冻结采样。
- 任务表单提供“正常写入、参数边界、错误返回、空结果、异常传播”五种模板、YAML 模板下载、文件上传和 AI 一键填写；适配器表单提供模板、文件上传与 AI 草案。所有快捷方式只填充可编辑内容，最终保存、登记与运行始终是独立人工操作。
