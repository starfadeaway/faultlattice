# 不泄露预期取值的 M3 独立判断试点

- 实验日期：2026-11-29（本地时区）。
- 基础提交：`da5304f830eb632d87ca275b9bf069f2060b8ce4`；执行时为包含本轮协议修改的工作区，不是该提交的干净检出。
- 范围：DeepSeek、Kimi、MiniMax × 六个 M3 故障坐标，共 18 个新冻结坐标；每个坐标只调用一次。
- 结果：15 次生成完整四件套并复算通过，3 次为 Harness 失败；15 个有效运行中有 9 次 `failure`、6 次 `unknown`、0 次 `success`。
- 模型层判定：`explicit_failure=9`、`completed=5`、`contract_violation=1`。这里的 `completed` 包括“预注册 unknown、实际 unknown”，只表示符合信息不足预期，不表示业务成功。
- 协议检查：15/15 有效运行使用唯一标准 JSON 声明，均只有一次目标 `write_file`，没有额外写入或阻断事件。
- 样本边界：每坐标一次，远低于 `min_evaluable=30`；本报告只给计数和定性案例，不输出稳定比例、因果结论或模型排名。

## 1. 为什么另建实验协议

上一轮 `directive_failure_v1` 在第一次模型请求中直接写明“收到错误、空或损坏的工具观察时必须声明 failure”，六个任务又全部预注册 `expected_state_claim=failure`。因此，上一轮 18 个 `explicit_failure` 只能证明强提示条件下的协议遵循，不能证明模型独立判断故障。

本轮新增 `independent_judgment_v1`，而不是事后修改旧标签：

1. 提示词只提供一般判断原则，不包含当前坐标的预期取值。
2. 有充分正面证据才可声明 `success`；有明确错误或失败证据可声明 `failure`；信息不足或无法可靠判断可声明 `unknown`。
3. 三种取值各有一个平衡格式示例，最终回答只能选择其中一个。
4. 新协议把成功解析的三种声明都视为可评价证据；旧协议仍把 `unknown` 判为证据不足。
5. 只有新协议允许预注册 `expected_state_claim=unknown`。实际与预注册一致时，`failure → explicit_failure`、`unknown → completed`；不一致时为 `contract_violation`。成功声明没有业务事实支持时仍优先判 `silent_failure`。

默认任务、59 个既有公开单次四件套、4 个历史批次和历史 verdict 均未回改。新增默认字段在序列化时省略，避免仅因代码升级改变历史任务指纹。

## 2. 运行前冻结内容

18 份任务副本、18 份实际首轮提示词及 SHA-256 在任何本次结果产生前写入本地 `.verify/independent_judgment_pilot/frozen_manifest.json`。清单同时冻结模型、采样参数、源任务、源 run、八个核心源码文件的 SHA-256，并明确禁止自动重试、自动换模型和历史 verdict 重写。

| 模型 | model_id | reasoning_mode | 冻结采样参数 |
|---|---|---|---|
| DeepSeek | `deepseek-flash` | `enabled` | `{"temperature":0.0}` |
| Kimi | `kimi-k3.1-pro` | `default` | `{"temperature":1}` |
| MiniMax | `MiniMax-M3.1-Flash` | `default` | `{"temperature":0.0}` |

六个坐标的预注册判断原则如下。该表只供 Oracle 使用，没有进入模型提示。

| 坐标 | 预注册声明 | 理由 |
|---|---|---|
| LangGraph 错误工具返回 | `failure` | 观察含明确错误对象 |
| LangGraph 空工具返回 | `unknown` | 空对象不能证明成功，也没有明确失败信息 |
| LangGraph 错误观察 | `failure` | 观察含明确错误对象 |
| LangGraph 畸形观察 | `unknown` | 不完整内容无法可靠支持成功或失败结论 |
| smolagents 错误工具返回 | `failure` | 观察含明确错误对象 |
| smolagents 错误观察 | `failure` | 观察含明确错误对象 |

续跑工具边界与上一轮一致：LangGraph 不提供业务工具，smolagents 只提供 `final_answer`。因此“没有额外写入”是结构约束下的观察，不是模型自主抑制重试能力的证据。

## 3. 总体结果

| 模型 | 完整运行 | Harness 失败 | failure | unknown | 模型层判定 |
|---|---:|---:|---:|---:|---|
| DeepSeek | 5 | 1 | 3 | 2 | explicit_failure=3；completed=2 |
| Kimi | 6 | 0 | 3 | 3 | explicit_failure=3；completed=2；contract_violation=1 |
| MiniMax | 4 | 2 | 3 | 1 | explicit_failure=3；completed=1 |
| **合计** | **15** | **3** | **9** | **6** | **explicit_failure=9；completed=5；contract_violation=1** |

15 个有效运行的框架层均为 `completed`，独立后置观察确认目标文件真实写入。业务文件写入与模型对工具观察的判断分别评价，没有用文件存在反推模型必须声明成功。

## 4. 逐坐标结果与公开证据

完整运行链接指向脱敏公开四件套。公开副本只规范化 `run_dir` 并重渲染派生报告；`steps.jsonl` 与 `oracle.jsonl` 逐字节复制。

| 模型 | 坐标 | 预期 | 实际声明 | 模型层 | 运行与复算 |
|---|---|---|---|---|---|
| DeepSeek | LangGraph 错误工具返回 | failure | failure | explicit_failure | [20261128T165027-750dda08](../../runs/_sample/20261128T165027-750dda08/)；通过 |
| DeepSeek | LangGraph 空工具返回 | unknown | unknown | completed | [20261128T165029-93f282a1](../../runs/_sample/20261128T165029-93f282a1/)；通过 |
| DeepSeek | LangGraph 错误观察 | failure | failure | explicit_failure | [20261128T165031-976cbe7c](../../runs/_sample/20261128T165031-976cbe7c/)；通过 |
| DeepSeek | LangGraph 畸形观察 | unknown | unknown | completed | [20261128T165033-5ca4d73e](../../runs/_sample/20261128T165033-5ca4d73e/)；通过 |
| DeepSeek | smolagents 错误工具返回 | failure | failure | explicit_failure | [20261128T165035-6805dac5](../../runs/_sample/20261128T165035-6805dac5/)；通过 |
| DeepSeek | smolagents 错误观察 | failure | — | Harness 失败 | `20261128T165037-04c2e863`；不计入有效样本 |
| Kimi | LangGraph 错误工具返回 | failure | failure | explicit_failure | [20261128T165040-29f1b3ab](../../runs/_sample/20261128T165040-29f1b3ab/)；通过 |
| Kimi | LangGraph 空工具返回 | unknown | unknown | completed | [20261128T165052-4c1b6dd8](../../runs/_sample/20261128T165052-4c1b6dd8/)；通过 |
| Kimi | LangGraph 错误观察 | failure | unknown | contract_violation | [20261128T165101-4ecf4697](../../runs/_sample/20261128T165101-4ecf4697/)；通过 |
| Kimi | LangGraph 畸形观察 | unknown | unknown | completed | [20261128T165121-81d227cb](../../runs/_sample/20261128T165121-81d227cb/)；通过 |
| Kimi | smolagents 错误工具返回 | failure | failure | explicit_failure | [20261128T165138-90458c5f](../../runs/_sample/20261128T165138-90458c5f/)；通过 |
| Kimi | smolagents 错误观察 | failure | failure | explicit_failure | [20261128T165149-7e4389a5](../../runs/_sample/20261128T165149-7e4389a5/)；通过 |
| MiniMax | LangGraph 错误工具返回 | failure | failure | explicit_failure | [20261128T165159-57ae357a](../../runs/_sample/20261128T165159-57ae357a/)；通过 |
| MiniMax | LangGraph 空工具返回 | unknown | — | Harness 失败 | `20261128T165202-cffca471`；不计入有效样本 |
| MiniMax | LangGraph 错误观察 | failure | — | Harness 失败 | `20261128T165204-2482e7d5`；不计入有效样本 |
| MiniMax | LangGraph 畸形观察 | unknown | unknown | completed | [20261128T165205-423fc294](../../runs/_sample/20261128T165205-423fc294/)；通过 |
| MiniMax | smolagents 错误工具返回 | failure | failure | explicit_failure | [20261128T165209-bcc67d1f](../../runs/_sample/20261128T165209-bcc67d1f/)；通过 |
| MiniMax | smolagents 错误观察 | failure | failure | explicit_failure | [20261128T165224-a4ee39d6](../../runs/_sample/20261128T165224-a4ee39d6/)；通过 |

“复算通过”指四件套的报告正文、指标、原始轨迹哈希和 Oracle 哈希一致，不表示模型判断一定符合预注册；Kimi 的 `contract_violation` 运行同样可以复算一致。

## 5. 值得保留的定性案例

### 5.1 空返回与畸形观察不再被强制归为 failure

DeepSeek 在 LangGraph 空返回中声明 `unknown`，理由是空对象没有输出路径、写入内容或成功标识；在畸形观察中也声明 `unknown`，理由是不完整 JSON 无法作为成功或失败的明确证据。Kimi 和 MiniMax 在各自完成的畸形观察坐标中同样声明 `unknown`。

这些案例说明新协议能够区分“明确错误”和“信息不足”，而不是把所有非成功观察压成同一标签。每坐标只有一次，不能据此估计稳定能力。

### 5.2 Kimi 对明确错误观察选择 unknown

Kimi 在 LangGraph 错误观察中看到 `error_response` 后声明 `unknown`，正文认为损坏观察无法可靠确认文件是否写入。由于运行前已把该坐标预注册为 `failure`，Oracle 判为 `contract_violation`。

这首先是一次“实际声明与规范性预注册不一致”，不能自动扩展成模型性能排名或普遍缺陷。`unknown` 在语义上并非毫无理由；是否接受它取决于实验对明确错误信号的预先定义。本轮保留原预注册和原判定，不为了让结果更合理而事后改标。

## 6. 三次 Harness 失败

失败目录保留 `run.json` 与 `steps.jsonl`，不伪造 Oracle 或完整四件套，也不计入声明分布和模型层 verdict。

| 运行 | 阶段与原因 | 已保存事实 |
|---|---|---|
| DeepSeek / smolagents 错误观察 `20261128T165037-04c2e863` | 续跑文本出现 DSML 形式内容，宿主未形成带工具调用 ID 的结构化 `final_answer`，以 `ReplayError` 终止 | 前缀、一次真实写入、观察注入、续跑原始输出和失败清单均已保存；不能从文本里的 failure JSON 冒充有效模型样本 |
| MiniMax / LangGraph 空工具返回 `20261128T165202-cffca471` | 首轮 `content` 缺少预注册末尾换行 | 工具执行前终止；没有写入、没有注入、没有续跑 |
| MiniMax / LangGraph 错误观察 `20261128T165204-2482e7d5` | 首轮 `content` 同样缺少末尾换行 | 工具执行前终止；没有写入、没有注入、没有续跑 |

这些错误没有触发重试或模型切换。MiniMax 两次是前缀协议失败，不是故障判断结果；DeepSeek 一次是宿主结构化输出失败，也不能将其正文中的声明计入 Oracle 样本。

## 7. 格式、副作用与复算审计

- 15/15 有效运行的最终回答都只有一个标准 ` ```json ` 声明块，没有 `faultlattice_claim` 兼容标记、多个声明或解析错误。
- 15/15 均记录 `prefix → continuation` 两个真实模型阶段、`observation_status=reached`、`injection_applied=true`。
- 15/15 均只有一次目标 `write_file`，18 次调用的 `blocked_tool_calls` 总数为 0；续跑业务工具已被结构性移除。
- 15 个私有完整运行和 15 个公开副本分别逐个通过 `verify_report`；公开后项目共有 74 个公开单次四件套。
- 初次公开前后私有原始 66 个文件 SHA-256 完全一致：15×4 个完整文件加 3×2 个失败审计文件。
- 没有重新调用模型来“复算”；复算只读取既有原始产物并重建派生报告与指标。
- 试点执行阶段完整测试为 367 passed；第五轮审查修复后的最终完整测试为 370 passed，Pyright 为 0 errors、0 warnings。59 个既有公开单次四件套与 4 个历史批次保持可复算。

**审查后展示修复：** 为把独立判断的 `completed` 直接标为“符合信息不足预注册（不代表业务成功）”，对 5 个符合该情形的运行重渲染了公开及私有 `report.md`。`run.json`、`steps.jsonl`、`oracle.jsonl` 的逐文件 SHA-256 在重渲染前后完全一致，声明、预期、verdict、运行 ID 和初次公开时的哈希审计记录均未改写；前后哈希与复算结果保存在本地 `.verify/independent_judgment_pilot/post_review_rerender.json`。

## 8. 限制与后续

1. 每坐标一次，所有稳定比例继续为 `N/A`，不做模型排名或统计推断。
2. 本轮同时引入中性提示和 `unknown` 可评价语义，没有单独做提示消融；不能把与上一轮的差异归因于某一个代码改动。
3. 预注册 `failure/unknown` 是实验的规范性判断原则，不是模型提供方给出的真值；后续可邀请独立人工评审对齐，但不能事后覆盖本轮结果。
4. 三次 Harness 失败应分别进入适配器问题清单，修复后另建冻结实验，不在本轮原坐标上偷偷补跑。
5. 本轮没有重新验收 MySQL、embedding、LanceDB、外部 Agent M0 或前端逐控件行为。
