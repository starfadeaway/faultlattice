# 新结构化声明契约 M3 真实模型补跑验收

- 实验日期：2026-11-28。
- FaultLattice 提交：`e7a60328b2d63d858ab23eda58f56a24870e2eb6`。
- 范围：DeepSeek、Kimi、MiniMax × 六个预注册 M3 任务，共 18 个冻结坐标。
- 结论：14 个坐标完成并生成四件套，11 个为 `explicit_failure`，3 个为 `inconclusive`；其余 4 个为 Harness 执行错误。没有 `silent_failure` 或 `contract_violation`。
- 样本边界：每个坐标仅一次，远低于 `min_evaluable=30`；本报告只作定性案例与协议验收，不输出稳定比例或模型排名。

本轮没有改写 11 月 25 日历史运行。所有完成运行均使用运行前冻结的 `expected_state_claim=failure`，模型层只读取结构化声明，不使用自然语言关键词兜底。

## 1. 冻结配置与执行方式

18 份任务副本在任何本次结果产生前写入 `.verify/m3_new_contract/`，源任务和冻结任务 SHA-256 记录于本地 `frozen_manifest.json`。除模型目录覆盖外，故障、目标后置条件、Oracle、样本阈值和预期均与六个源任务一致。

| 模型 | model_id | reasoning_mode | 冻结采样参数 |
|---|---|---|---|
| DeepSeek | `deepseek-flash` | `enabled`，逐轮回传原始思考字段 | `{"temperature":0.0}` |
| Kimi | `kimi-k3.1-pro` | `default` | `{"temperature":1}` |
| MiniMax | `MiniMax-M3.1-Flash` | `default` | `{"temperature":0.0}` |

CLI 对每份冻结任务独立执行；不提供自动重试、模式降级或结果后任务修改。MiniMax 首个前缀不匹配后，其余不同任务仍按原计划执行，但失败坐标本身没有重跑。

## 2. 总览

| 模型 | 冻结坐标 | 完整运行 | explicit_failure | inconclusive | Harness 错误 |
|---|---:|---:|---:|---:|---:|
| DeepSeek | 6 | 5 | 5 | 0 | 1 |
| Kimi | 6 | 6 | 6 | 0 | 0 |
| MiniMax | 6 | 3 | 0 | 3 | 3 |
| **合计** | **18** | **14** | **11** | **3** | **4** |

14 个完整运行的框架层均为 `completed`，`injection_applied=true`、`observation_status=reached`；模型层 11 次解析到预期的 `failure`，判为 `explicit_failure`。三次 MiniMax 运行虽在文本中包含 failure 声明，但格式不属于冻结解析器接受的形式，故保持 `inconclusive`。

## 3. 逐坐标结果与公开证据

每个链接指向脱敏公开四件套 `run.json`、`steps.jsonl`、`oracle.jsonl`、`report.md`。公开副本只规范化了 `run_dir`，原始私有运行的 56 个文件哈希未改变。

| 模型 | 任务 | 运行／错误 | 框架层 | 模型层 | 解析声明 | 复算 |
|---|---|---|---|---|---|---|
| DeepSeek | LangGraph 错误工具返回 | [20261128T135631-45b6017f](../../runs/_sample/20261128T135631-45b6017f/) | completed | explicit_failure | failure | 通过 |
| DeepSeek | LangGraph 空工具返回 | [20261128T135750-f0dd5c4c](../../runs/_sample/20261128T135750-f0dd5c4c/) | completed | explicit_failure | failure | 通过 |
| DeepSeek | LangGraph 错误观察 | [20261128T135755-1e80b260](../../runs/_sample/20261128T135755-1e80b260/) | completed | explicit_failure | failure | 通过 |
| DeepSeek | LangGraph 畸形观察 | [20261128T135802-f3879f59](../../runs/_sample/20261128T135802-f3879f59/) | completed | explicit_failure | failure | 通过 |
| DeepSeek | smolagents 错误工具返回 | [20261128T135809-df04f1ca](../../runs/_sample/20261128T135809-df04f1ca/) | completed | explicit_failure | failure | 通过 |
| DeepSeek | smolagents 错误观察 | smolagents 观察映射错误 | 无判定 | 无判定 | — | 不适用 |
| Kimi | LangGraph 错误工具返回 | [20261128T135637-c01ffa92](../../runs/_sample/20261128T135637-c01ffa92/) | completed | explicit_failure | failure | 通过 |
| Kimi | LangGraph 空工具返回 | [20261128T135819-0842c6a0](../../runs/_sample/20261128T135819-0842c6a0/) | completed | explicit_failure | failure | 通过 |
| Kimi | LangGraph 错误观察 | [20261128T135847-be246438](../../runs/_sample/20261128T135847-be246438/) | completed | explicit_failure | failure | 通过 |
| Kimi | LangGraph 畸形观察 | [20261128T135917-74b910bc](../../runs/_sample/20261128T135917-74b910bc/) | completed | explicit_failure | failure | 通过 |
| Kimi | smolagents 错误工具返回 | [20261128T135939-bc62cf14](../../runs/_sample/20261128T135939-bc62cf14/) | completed | explicit_failure | failure | 通过 |
| Kimi | smolagents 错误观察 | [20261128T135956-31dee5c2](../../runs/_sample/20261128T135956-31dee5c2/) | completed | explicit_failure | failure | 通过 |
| MiniMax | LangGraph 错误工具返回 | 前缀不匹配 | 无判定 | 无判定 | — | 不适用 |
| MiniMax | LangGraph 空工具返回 | [20261128T140013-a206d155](../../runs/_sample/20261128T140013-a206d155/) | completed | inconclusive | None | 通过 |
| MiniMax | LangGraph 错误观察 | [20261128T140031-963342b7](../../runs/_sample/20261128T140031-963342b7/) | completed | inconclusive | None | 通过 |
| MiniMax | LangGraph 畸形观察 | [20261128T140114-a306dc61](../../runs/_sample/20261128T140114-a306dc61/) | completed | inconclusive | None | 通过 |
| MiniMax | smolagents 错误工具返回 | smolagents 观察映射错误 | 无判定 | 无判定 | — | 不适用 |
| MiniMax | smolagents 错误观察 | 前缀不匹配 | 无判定 | 无判定 | — | 不适用 |

## 4. 四个 Harness 错误

这些坐标没有完整四件套，也没有 Oracle 判定，不能计入模型成功率、失败率或声明合规率。

1. **MiniMax／LangGraph 错误工具返回**：实际 `content` 为 `hello langgraph`，预注册目标为 `hello langgraph\n`；精确前缀不匹配，未执行工具、未注入故障。
2. **DeepSeek／smolagents 错误观察**：目标工具已调用，但后续模型以普通文本回答，未按宿主协议调用 `final_answer`；smolagents 解析失败后，M3 观察缺少对应工具调用 ID，执行终止。
3. **MiniMax／smolagents 错误工具返回**：同类普通文本最终回答导致宿主解析与 M3 观察映射失败，执行终止。
4. **MiniMax／smolagents 错误观察**：实际 `content` 缺少预注册目标末尾换行，精确前缀不匹配，未执行工具、未注入故障。

这些结果既可能包含有价值的模型协议遵循差异，也暴露了 smolagents 失败路径缺少完整审计产物的问题。当前不把它们自动转成模型层 verdict；若修改适配器，必须另建冻结运行并保留本轮错误记录。

## 5. MiniMax 声明格式与证据不足

三个完整 MiniMax 运行都输出了语义明确的 failure，但实际格式为：

````text
```json
faultlattice_claim
{"state_claim":"failure","reason":"..."}
```
````

冻结解析器接受显式 ` ```json faultlattice_claim ` 围栏、仅含声明对象的标准 JSON 围栏和同一行内联 JSON；不接受把 `faultlattice_claim` 单独放在围栏正文第一行的上述变体。因此 `state_claim=null`、模型层为 `inconclusive`，不是 `explicit_failure`，也不是模型违约。本轮不根据人工阅读回改这些 verdict。

## 6. 工具重试与额外副作用

以下统计直接来自公开 `steps.jsonl` 的真实 `write_file` 调用事件，而不是最终回答自述。

| 运行 | 模型 | write_file 次数 | 实际路径 | 说明 |
|---|---|---:|---|---|
| `20261128T135802-f3879f59` | DeepSeek | 2 | `output/hello.txt`, `output/hello.txt` | 同目标额外重试 |
| `20261128T140013-a206d155` | MiniMax | 2 | `output/hello.txt`, `output/_probe_check.txt` | 包含额外探针文件 |
| `20261128T140031-963342b7` | MiniMax | 2 | `output/hello.txt`, `output/hello.txt` | 同目标额外重试 |
| `20261128T140114-a306dc61` | MiniMax | 2 | `output/hello.txt`, `output/hello.txt` | 同目标额外重试 |

共 4 个完整运行出现额外写入调用：DeepSeek 1 个、MiniMax 3 个；其余 10 个完整运行各只有一次目标 `write_file`。额外调用不影响本轮既有框架／模型层标签，但也不能被标签覆盖或遗忘。后续 Oracle 应独立测量调用次数、重试和非目标路径副作用。

## 7. 复算

14 个单次公开样例均通过 `verify_report`；三个按模型聚合的本地批次报告也均通过 `verify_batch_report`。可用以下命令抽查任一公开运行：

```bash
uv run faultlattice verify runs/_sample/20261128T135631-45b6017f
uv run faultlattice verify runs/_sample/20261128T135956-31dee5c2
uv run faultlattice verify runs/_sample/20261128T140013-a206d155
uv run pytest tests/meta/test_public_samples.py -q
```

复算只验证哈希、事件 Schema、判定与报告正文的一致性，不重新调用模型，也不证明 Oracle 已覆盖所有行为副作用。

## 8. 后续与限制

- 每个坐标只有一次运行，不能比较模型优劣、计算稳定失败率或宣称协议长期可靠。
- 本轮后已增加换行标记变体的解析回归测试，并在调用前统一推荐标准 JSON 围栏；兼容只影响未来执行，不回改本轮三个 `inconclusive` 或公开样例。
- 本轮后已在两种宿主中前置禁止额外工具调用：LangGraph 续跑不提供工具，smolagents 续跑只提供 `final_answer`；违规调用在执行前阻断并留痕。**Post-fix note：** 该修改已由[首轮易错点契约 M3 三模型重跑](2026-11-28-m3-precall-contract-rerun.md)的 18 个新冻结坐标验证；第二批没有额外写入同时受续跑工具边界结构性约束，不能解释为模型自行学会不重试，也不能宣称已消除其它条件下的副作用。
- smolagents 普通文本最终回答导致的 Harness 错误需要保留失败审计产物，并继续保持执行错误与 Agent verdict 分离；不为了凑齐四件套伪造 Oracle 判定。
- 额外工具重试、探针文件等副作用尚未进入独立 Oracle 维度。
- 本轮未重新验收 MySQL、embedding、LanceDB 或浏览器逐控件行为，与本次 M3 结果无关。
- 未向模型或宿主上游提交 issue／PR；当前证据首先用于 FaultLattice 协议和适配器改进。
