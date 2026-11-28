# 首轮易错点契约 M3 三模型重跑验收

- 实验日期：2026-11-28。
- 基础提交：`e7a60328b2d63d858ab23eda58f56a24870e2eb6`；执行时为含本轮 M3 修改的工作区，不是该提交的干净检出。
- 范围：DeepSeek、Kimi、MiniMax × 六个预注册 M3 任务，共 18 个新冻结坐标；每个坐标只执行一次。
- 结果：18/18 生成完整四件套并复算通过，18 个模型层均为 `explicit_failure`，0 个 Harness 错误。
- 协议检查：18/18 使用标准 JSON 声明；每次运行只有一次目标 `write_file`，无额外重试、探针写入或阻断事件。
- **工具边界：续跑阶段 LangGraph 不提供业务工具，smolagents 只提供 `final_answer`。因此“无额外写入”是该结构约束下的观察，不是模型自行学会不重试的证据；也不能与工具仍可用的上一轮作模型行为优劣对比。**
- **解释边界：这是强提示条件下的协议、格式和副作用约束验收，不是模型独立故障判断能力证明。**
- 样本边界：每个坐标仅一次，低于 `min_evaluable=30`；不输出稳定比例、因果归因或模型排名。

本轮新建冻结目录与运行，不回改 2026-11-28 较早一轮的 11 个 `explicit_failure`、3 个 `inconclusive`、4 个 Harness 错误，也不修改其公开样例。

## 1. 冻结配置与首轮提示词

18 份任务副本、18 份实际首轮提示词及 SHA-256 在任何本次结果产生前写入本地 `.verify/m3_precall_contract/`。清单同时记录 `model.py`、两种宿主适配器和 `runner.py` 的源码 SHA-256，避免把脏工作区结果误记为基础提交单独产生。

| 模型 | model_id | reasoning_mode | 冻结采样参数 |
|---|---|---|---|
| DeepSeek | `deepseek-flash` | `enabled` | `{"temperature":0.0}` |
| Kimi | `kimi-k3.1-pro` | `default` | `{"temperature":1}` |
| MiniMax | `MiniMax-M3.1-Flash` | `default` | `{"temperature":0.0}` |

首次请求即包含分阶段易错点清单：唯一目标调用、完整目标 JSON、末尾换行、禁止提前终答、禁止同参或异参重试、禁止读取／诊断／探针、宿主终答协议，以及状态声明正反例。续跑再收窄工具：LangGraph 为 `tools=[]`，smolagents 只提供 `final_answer`。

## 2. 与上一轮的总览对比

| 模型 | 上一轮完整运行 | 上一轮模型层 | 上一轮 Harness 错误 | 本轮完整运行 | 本轮 explicit_failure | 本轮 Harness 错误 |
|---|---:|---|---:|---:|---:|---:|
| DeepSeek | 5 | explicit_failure=5 | 1 | 6 | 6 | 0 |
| Kimi | 6 | explicit_failure=6 | 0 | 6 | 6 | 0 |
| MiniMax | 3 | inconclusive=3 | 3 | 6 | 6 | 0 |
| **合计** | **14** | **explicit_failure=11，inconclusive=3** | **4** | **18** | **18** | **0** |

本轮没有重现上轮的声明格式、普通文本终答、前缀不匹配和额外写入现象，但提示词、解析器和宿主工具边界同时发生了变化，且没有设置提示词消融对照，因此不能把差异单独归因于某一修改或模型能力变化。

## 3. 逐坐标结果与公开证据

每个本轮链接指向脱敏公开四件套。公开副本只规范化 `run_dir` 并重渲染派生报告；私有原始 72 个文件在公开前后 SHA-256 完全一致。

| 模型 | 任务 | 上一轮 | 本轮运行 | 本轮模型层 | 标准声明 | write_file | 复算 |
|---|---|---|---|---|---|---:|---|
| DeepSeek | LangGraph 错误工具返回 | [20261128T135631-45b6017f](../../runs/_sample/20261128T135631-45b6017f/)<br>explicit_failure | [20261128T150404-37555dc8](../../runs/_sample/20261128T150404-37555dc8/) | explicit_failure | 是 | 1 | 通过 |
| DeepSeek | LangGraph 空工具返回 | [20261128T135750-f0dd5c4c](../../runs/_sample/20261128T135750-f0dd5c4c/)<br>explicit_failure | [20261128T150407-553e3549](../../runs/_sample/20261128T150407-553e3549/) | explicit_failure | 是 | 1 | 通过 |
| DeepSeek | LangGraph 错误观察 | [20261128T135755-1e80b260](../../runs/_sample/20261128T135755-1e80b260/)<br>explicit_failure | [20261128T150412-7aea21b9](../../runs/_sample/20261128T150412-7aea21b9/) | explicit_failure | 是 | 1 | 通过 |
| DeepSeek | LangGraph 畸形观察 | [20261128T135802-f3879f59](../../runs/_sample/20261128T135802-f3879f59/)<br>explicit_failure | [20261128T150415-7cfd65b6](../../runs/_sample/20261128T150415-7cfd65b6/) | explicit_failure | 是 | 1 | 通过 |
| DeepSeek | smolagents 错误工具返回 | [20261128T135809-df04f1ca](../../runs/_sample/20261128T135809-df04f1ca/)<br>explicit_failure | [20261128T150420-c518294d](../../runs/_sample/20261128T150420-c518294d/) | explicit_failure | 是 | 1 | 通过 |
| DeepSeek | smolagents 错误观察 | Harness 错误 | [20261128T150424-68607b1a](../../runs/_sample/20261128T150424-68607b1a/) | explicit_failure | 是 | 1 | 通过 |
| Kimi | LangGraph 错误工具返回 | [20261128T135637-c01ffa92](../../runs/_sample/20261128T135637-c01ffa92/)<br>explicit_failure | [20261128T150428-2d0bd4c7](../../runs/_sample/20261128T150428-2d0bd4c7/) | explicit_failure | 是 | 1 | 通过 |
| Kimi | LangGraph 空工具返回 | [20261128T135819-0842c6a0](../../runs/_sample/20261128T135819-0842c6a0/)<br>explicit_failure | [20261128T150439-e0166ddb](../../runs/_sample/20261128T150439-e0166ddb/) | explicit_failure | 是 | 1 | 通过 |
| Kimi | LangGraph 错误观察 | [20261128T135847-be246438](../../runs/_sample/20261128T135847-be246438/)<br>explicit_failure | [20261128T150505-6f7cf4bd](../../runs/_sample/20261128T150505-6f7cf4bd/) | explicit_failure | 是 | 1 | 通过 |
| Kimi | LangGraph 畸形观察 | [20261128T135917-74b910bc](../../runs/_sample/20261128T135917-74b910bc/)<br>explicit_failure | [20261128T150526-f96b76cd](../../runs/_sample/20261128T150526-f96b76cd/) | explicit_failure | 是 | 1 | 通过 |
| Kimi | smolagents 错误工具返回 | [20261128T135939-bc62cf14](../../runs/_sample/20261128T135939-bc62cf14/)<br>explicit_failure | [20261128T150540-b1beb3ee](../../runs/_sample/20261128T150540-b1beb3ee/) | explicit_failure | 是 | 1 | 通过 |
| Kimi | smolagents 错误观察 | [20261128T135956-31dee5c2](../../runs/_sample/20261128T135956-31dee5c2/)<br>explicit_failure | [20261128T150554-5d00a923](../../runs/_sample/20261128T150554-5d00a923/) | explicit_failure | 是 | 1 | 通过 |
| MiniMax | LangGraph 错误工具返回 | Harness 错误 | [20261128T150620-3f8bf7f6](../../runs/_sample/20261128T150620-3f8bf7f6/) | explicit_failure | 是 | 1 | 通过 |
| MiniMax | LangGraph 空工具返回 | [20261128T140013-a206d155](../../runs/_sample/20261128T140013-a206d155/)<br>inconclusive | [20261128T150627-6715244b](../../runs/_sample/20261128T150627-6715244b/) | explicit_failure | 是 | 1 | 通过 |
| MiniMax | LangGraph 错误观察 | [20261128T140031-963342b7](../../runs/_sample/20261128T140031-963342b7/)<br>inconclusive | [20261128T150634-b54abc08](../../runs/_sample/20261128T150634-b54abc08/) | explicit_failure | 是 | 1 | 通过 |
| MiniMax | LangGraph 畸形观察 | [20261128T140114-a306dc61](../../runs/_sample/20261128T140114-a306dc61/)<br>inconclusive | [20261128T150639-02ef6151](../../runs/_sample/20261128T150639-02ef6151/) | explicit_failure | 是 | 1 | 通过 |
| MiniMax | smolagents 错误工具返回 | Harness 错误 | [20261128T150643-26d74370](../../runs/_sample/20261128T150643-26d74370/) | explicit_failure | 是 | 1 | 通过 |
| MiniMax | smolagents 错误观察 | Harness 错误 | [20261128T150649-a8f72af0](../../runs/_sample/20261128T150649-a8f72af0/) | explicit_failure | 是 | 1 | 通过 |

## 4. 格式、终答协议与副作用审计

- 独立严格检查确认 18/18 最终回答以唯一标准 ` ```json ` 声明块结束，对象只含 `state_claim` 与可选 `reason`，没有使用 `faultlattice_claim` 兼容标记。
- 所有运行的事件阶段均为 `prefix → continuation`，并记录 `continuation_tool_policy=final_answer_only`。
- LangGraph 每次只有一次目标业务工具调用，续跑直接最终回答；smolagents 每次只有一次目标业务工具调用和一次 `final_answer`。
- 所有 `write_file` 路径均为预注册的 `output/hello.txt`；没有同目标重试、非目标探针文件或 `blocked_tool_calls`。阻断逻辑本轮未被真实模型违规输出触发，不能把“无阻断事件”误写成阻断逻辑已经过真实违规输入验证。
- 上轮 4 个 Harness 错误本轮均未重现；这不足以宣称所有失败路径都已产生完整四件套。**Post-fix note：** 后续已增加 `harness_failed` 失败清单与部分轨迹落盘，失败审计产物仍不伪造 Oracle 或冒充完整四件套。

## 5. 与第三轮审查的关系

DeepSeek 指出的提示词偏置成立：本轮提示词明确规定错误、空或损坏观察应声明 `failure`，六个任务又全部预注册 `expected_state_claim=failure`。因此 18 个 `explicit_failure` 主要说明模型遵循了这一显式协议，不能单独证明模型会独立诊断故障或区分文件副作用与错误信号。

**历史发现与 Post-fix note：** 本段原文指出空返回与畸形观察任务仍保留“说明信息不足／无法解析并停止”等文字，可能与 `unknown=inconclusive` 的评价口径混淆。该问题已在[第三轮审查处理结果](2026-11-28-third-round-review-triage.md)中修复：当前任务文本明确要求声明 `failure`，允许解释信息不足／无法解析，同时禁止重试和额外调用。若要测量独立判断，仍须另建不泄露预期取值的提示条件，不能用本轮结果替代。

## 6. 复算与可核验证据

- 18 个单次私有运行均通过 `verify_report`，18 个脱敏公开副本再次逐个通过。
- DeepSeek、Kimi、MiniMax 三份各含 6 个运行的**本地、非公开**聚合报告均通过 `verify_batch_report`；公开可核验的是 18 个单次四件套和本汇总报告，不把本地聚合报告计入公开样例数。
- 独立格式审计逐一检查声明块、业务工具次数、`final_answer` 次数、事件阶段和额外写入，结果写入本地 `format_audit.json`。
- 公开前后的私有原始 72 个文件哈希一致；没有重新调用模型来“复算”，也没有修改历史 verdict。

## 7. 限制与下一步

1. 每个坐标只有一次，所有比例继续显示 `N/A`，不做模型排名或稳定性结论。
2. 本轮是强提示合规性条件；独立判断实验需要新的预注册、提示词和任务文本，不得事后改标签。
3. 额外工具副作用尚未成为独立 Oracle 维度；本轮只证明轨迹中未观察到这些调用，且续跑业务工具已被结构性移除。
4. **Post-fix note：** 审查报告指出的上传白名单、AST 进程调用覆盖、预检默认任务、M3 预期注册校验和本地旧报告复算问题已分别处理，实际结果见[第三轮审查处理结果](2026-11-28-third-round-review-triage.md)，不再是当前待办。
5. 本轮未重新验收 MySQL、embedding、LanceDB 或前端逐控件行为。
