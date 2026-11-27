# FaultLattice

> Agent Reliability Harness & Evaluation Platform

FaultLattice 是一个 Agent 可靠性注入实验与评测工具：对宿主 Agent 框架执行受控故障注入、轨迹记录与重放，并用预注册的 Oracle 判定框架层与模型层行为，产出可复算的实验报告。

## 快速安装与运行

要求：Python >= 3.13、uv；研发视图还需要 Node.js 与 npm。

```bash
uv sync
uv run faultlattice --help
uv run pytest
```

依赖与环境统一由 uv 管理（`pyproject.toml` + `uv.lock`），不混用 venv+pip 工作流。

## 研发控制台

```bash
npm ci --prefix console/web
uv run python run_all.py
# 也可分别启动：--only server / --only client
# 自定义 FastAPI 端口：--port 8001；自定义 Vite 端口：--client-port 5173
```

打开 `http://127.0.0.1:5173/`。后端使用 reload，前端使用 Vite HMR；Ctrl+C 统一清理子进程。服务仅绑定回环地址，不对外开放。

主导航支持两种可切换形式：领域分组保留监测、实验、分析、接入和设置，监测区包含项目地图、模块与源码、命名登记、真实测试状态和实验产物五个子页面；独立页面则把上述常用功能和设置直接列入主导航，并隐藏重复的监测子页。实验区提供实验对象选择、预注册任务、一键套件、运行进度、事件时间线、Oracle 判定和历史恢复。分析页对真实历史做跨批次文本／对象／层级筛选，提供带动效、浮动反馈与悬浮明细的判定环图、批次风险趋势和任务风险图，并用固定规则输出中文数据结论。所选对话模型还可基于聚合证据生成跨批次分析；不发送完整轨迹、源码或密钥，筛选变化会标记旧结论的适用范围。页面可跳转原始批次，并分别下载完整分析与模型分析 Markdown；不会重新执行实验，也不把 Harness 完成解释为 Agent 无缺陷。顶部“查找功能”或 Ctrl／Cmd+K 可搜索并跳转到全部页面和接入动作。界面支持明暗主题、自定义强调色、代码语法高亮与逐文件中文说明；命名文档、单次实验报告和套件报告均可下载 Markdown。`project.manifest.yaml` 只维护模块、路径、`required_checks` 与依赖；`developing / verified` 由实际验收结果自动推导。

设置页集中管理外观、动效、界面密度、代码字号、本地／UTC 时间、默认首页、导航形式、运行刷新间隔和环境诊断，并提供页面空闲预加载、回顶按钮、代码自动换行、高对比度及偏好 JSON 导出／校验导入。实验流程设置还包括默认对话模型（同时作为 M3 与建议生成的初始选择）、经浏览器授权的批次完成系统通知，以及启动后是否自动定位结果；通知只描述执行状态，不宣称 Agent 通过。导航与实验交互选择会持久化；旧版不含新增可选字段的偏好文件仍可导入。偏好仅保存在当前浏览器，恢复默认保留模型选择，不删除实验历史或适配器登记。

实验页先选择“内置参考宿主与标准套件”或当前预检通过的外部 Agent，再选择自动匹配的兼容任务并运行；M0 不调用真实模型，M3 才使用启动前选定的模型。历史结果可按对象、批次和任务筛选。实验页不会把 Harness 执行成功误写成被测 Agent 无缺陷：`silent_failure` 等判定是实验结果，配置或适配器异常才属于执行错误。套件定义位于 `experiments/suites.yaml`，状态与套件报告保存在 `runs/suites/<batch_id>/`。

每个已完成任务可生成 LLM 修改建议。建议模型读取预注册契约、实际轨迹和 Oracle，输出问题证据、代码或提示词修改方向及回归测试；结果随套件历史保存并可下载 Markdown，不自动修改源码或判定。实验页的同一个模型选择同时作为 M3 与建议的默认模型：只允许启动前选择，M3 启动时冻结实际模型 ID 和原任务采样参数，执行中不可更改。也可使用 `FAULTLATTICE_MODEL_API_KEY` / `FAULTLATTICE_MODEL_BASE_URL` 兼容端点与显式的 `FAULTLATTICE_ADVISOR_MODEL_ID`，避免意外调用。

## 外部 Agent 接入

“接入”页面向实现 `HostAdapter` 的本地 Python 宿主，不是普通聊天模型端点，也不是任意黑盒程序的自动包装器。参考适配器位于 `examples/external_agent/reference_agent.py`，三个不同能力边界的实例默认登记在 `external_agents/registry.yaml`。

接入页提供“完整参考循环”“参数边界”“工具结果”三种模板和“自定义适配器”参考样式。`ReferenceAgent` 支持 `tool_args` 与 `tool_result`；`ToolArgsReferenceAgent` 只支持参数注入；`ToolResultReferenceAgent` 只支持工具结果注入。下拉模板只填写可编辑字段，不会自动登记或启动实验；自定义样式使用统一的高亮代码块展示最小类结构，生产接入仍应实现自己的真实 `run_script(...)`。登记、任务创作与已登记宿主位于三个子页面，切换时保留未提交表单；三个预置宿主均可打开与模块页一致的 Python 分色、行号源码抽屉。

1. 直接选择上传明确信任的 `.py` 适配器，或把源码放入项目目录；实现 `capabilities`、`preflight(fault)` 与 `run_script(...)`，M3 还需要实现 `CounterfactualHost`。
2. 在草案队列查看代码、说明与警告并填写类名，确认保存后，再在登记表中核对项目内相对 `.py` 路径和可无参实例化的类名。系统会真实加载模块，核对执行模式、注入点、工具能力和宿主版本，并记录源码 SHA-256。
3. 从实际兼容的预注册任务中选择测试；启动后复用同一后台执行、四件套、报告复算、历史恢复和 LLM 建议流程。

登记与预检会执行模块顶层代码和构造函数，因此只能接入可信源码。路径越界、能力不符或缺少 `injection.original / replacement / applied` 有效证据都会显式失败；故障任务没有真实注入证据时按 Harness 错误关闭，并保留已生成的轨迹，不计为有效故障样本。外部适配器仍需自行把宿主真实行为转换成契约事件，系统不会凭最终回答猜测内部执行过程。只有当前预检通过的宿主才陈列在“已登记宿主”。

### 任务创作与 AI 草案

- “按能力生成标准任务包”读取宿主真实预检结果：完整参考宿主生成无故障基线、非法参数、错误返回、空结果和工具异常 5 项；只支持参数注入的宿主只生成基线与非法参数 2 项。重复生成跳过已有文件，不会自动执行。
- 任务文件通过真实文件选择器上传 `.yaml/.yml/.json`，也可下载 YAML 模板。导入只解析到可编辑表单，不自动保存或运行；支持简化 `TaskDraft` 与当前兼容的完整 M0 `TaskDefinition`。
- 自定义任务保存到 `tasks/custom/*.yaml`，来源标为 `custom`，并按执行模式、工具、注入点和 `preflight` 自动出现在所有兼容宿主下。当前只开放 M0 与确定性 `file_written` Oracle，`oracle.validation=unvalidated`；保存后仍需用户显式运行，删除任务不删除历史产物。
- 五种确定性模板和“AI 生成任务草案”都只填充可编辑表单。AI 返回的 JSON 必须先通过字段、路径和宿主能力校验，再经用户显式保存才会成为预注册任务；AI 不参与 Oracle，也不会根据实验结果反向修改预期。AI 草案、保存操作和已预注册任务进入同一任务队列，右侧显示加载、完成或失败状态，详情抽屉展示工具参数、故障、文件证据、Oracle 和样本阈值。
- “AI 适配器草案”既可直接选择上传 README、说明文档和源码，也可在高级区使用项目内路径；允许 `.md/.txt/.py/.yaml/.yml/.json/.toml` UTF-8 文件。上传原件保存到已忽略提交的 `external_agents/uploads/<uuid>/`，上传本身不调用模型。单次生成最多使用 6 个文件，单文件 10,000 字符、总计 30,000 字符进入模型；界面列出实际读取量、截断状态和按字符估算的输入 Token，估算值不是提供方账单。
- 所有资料都放在不可信数据边界内，模型不执行其中的命令。返回 Python 只做 AST 语法、顶层适配器类和危险调用检查，辅助类不会因位置靠前而冒充适配器；信息不足必须保留 TODO。草案可下载，或显式保存到 `external_agents/drafts/<agent-id>.py`，已有文件拒绝覆盖。保存仍不等于登记，只有再次执行“真实加载并登记”才会运行模块顶层代码和构造函数。
- 本地上传与 AI 生成共用适配器队列，详情默认使用带语言标识和行号的高亮代码块，编辑代码需显式切换。失败或信息不足时可补充说明后重新生成；只有新草案成功才替换旧草案，确认保存不会自动登记。
- 草案使用用户选定的 chat 模型，保留其思考模式，合并 `_ADVISOR_SAMPLING_PARAMS`，但不改动 M3 冻结采样。适配器与任务草案分别使用 16,000 / 8,000 的有限输出 Token 上限和 120 秒超时，不自动重试；空正文、语法错误或契约不符会明确失败，不伪造成功草案。

## smolagents 宿主与 M3

```bash
# 可选宿主依赖固定为 smolagents 1.26.0；核心和本地宿主不要求安装它。
uv sync --group smolagents --group models
uv run faultlattice run tasks/smolagents_write.yaml

# M3 由真实模型建立目标调用，再从工具错误或观察损坏后续跑。
uv run faultlattice run tasks/smolagents_m3.yaml
uv run faultlattice run tasks/smolagents_m3_observation_error.yaml
```

适配器使用真实 `ToolCallingAgent`，支持 M0–M2 的 `tool_args`、`tool_result` 与 `observation` 注入，以及 M3 的 `tool_result / observation` 续跑。M0 脚本只提供预设输出，不调用真实模型。M3 通过 `StructuredLiveModel` 连接所选 `ModelProvider`，通过 `StructuredMemoryAgent` 保留结构化工具调用 ID 和原始思考字段；最终回答仍由 smolagents 的 `final_answer` 工具结束。运行前会核对精确版本和上游注入点签名；版本或签名变化会显式失败。

## LangGraph 宿主与 M3

```bash
# 第二个异构宿主固定为 LangGraph 1.2.24，按需安装。
uv sync --group langgraph --group models
uv run faultlattice run tasks/langgraph_write.yaml

# M3 读取 M0 源轨迹中的目标契约，由真实模型建立前缀并续跑。
uv run faultlattice run tasks/langgraph_m3.yaml
```

适配器使用真实 `StateGraph + ToolNode`，支持 M0–M2 的三类注入与 M3 续跑。预设模型节点只生成 `AIMessage`；真实图路由、Pydantic 参数校验、工具执行和消息状态合并由 LangGraph / LangChain 完成。观察注入会改写下一轮模型节点实际收到的 `ToolMessage.content`，而非只修改日志。

两种宿主的 M3 源 run 均只读，只提供目标工具调用和故障契约。本次真实模型先生成名称、参数完全匹配的唯一调用，再执行工具与故障注入；DeepSeek 思考模式将原始 `reasoning_content` 写入真实宿主消息和结构化轨迹，并在后续工具请求中完整回传。前缀不匹配或思考字段缺失时在工具执行前终止，不自动重试、伪造或关闭思考。控制台在启动前冻结模型、思考模式和采样参数。伪模型测试只证明协议接线，真实模型结果必须另行运行。

## 当前已实现能力

- 核心 schema（Pydantic v2）：FaultSpec 合法组合校验、任务预注册、轨迹事件、Oracle 判定记录、run.json 运行清单；
- 故障模型：13 种合法组合（spec 第 3 节），非法组合直接报配置错误；
- Oracle 判定器：框架层 / 模型层判定树，配 10 个 golden cases 与元测试；
- canonical JSON（排序键 / UTF-8 / LF / 禁 NaN）、SHA-256、原子写入，双平台测试；
- CLI 纵向切片：`run` / `replay`（M1 纯轨迹、M2 故障注入）/ `report` / `verify`；
- M3 反事实续跑协议、OpenAI 兼容模型适配器、双层 Oracle 与源轨迹防篡改校验；
- 批次闭环：`run-batch` 运行前 A/B 硬校验，`batch-report` 跨运行分层聚合，`batch-verify` 独立复算；
- 批次指标遵循 `min_evaluable` 与 inconclusive 阈值门禁，不足时沉默失败率显示 `N/A`；
- 本地受控测试宿主（确定性工具调用程序，支持 tool_args / tool_result 注入）；
- 本地同步工具真实进程硬超时：独立 spawn 进程、到期 terminate／必要时 kill、join 回收、实际耗时与 PID 证据；
- smolagents 1.26.0 真实宿主（支持 tool_args / tool_result / observation，含 CLI、M2 重放与 M3 结构化消息续跑）；
- LangGraph 1.2.24 异构真实宿主（StateGraph / ToolNode，含参数校验、CLI、M2 重放与 M3 协议）；
- FastAPI + React 研发与实验视图、预注册一键套件、过程事件和 Markdown 报告下载；
- MySQL 事务型可重建结构索引、LanceDB 覆盖重建与 cosine 相似故障检索；
- 原始四件套 baseline / current 回归质量门禁及 Markdown 审计报告；
- AST 依赖方向检查、仓库卫生检查、GitHub Actions CI（ubuntu + windows）。

真实进程硬超时可直接运行；旧的同步工具任务仍默认使用立即模拟 `TimeoutError`，不会改变既有实验口径：

```bash
uv run faultlattice run tasks/local_hard_timeout.yaml
```

## 真实外部依赖验收

以下均为本机单次小样本验收：模型实验与初次依赖验收执行于 2026-11-25，MySQL、真实 embedding 和 LanceDB 于 2026-11-26 再次只读核对或真实查询。它们只证明这些坐标下实际执行过，不能解释为模型的稳定性能或可靠性排名。完整命令、依赖版本、结果与限制见 [外部依赖验收报告](reports/external/2026-11-26-external-dependency-acceptance.md)，也可在实验产物页在线阅读或下载 Markdown。

| 验收项 | 实际结果 |
|---|---|
| DeepSeek M3 | 批次 `20261125T140940-c9f18d13`：4/4 任务完成、4/4 故障观察到达，四项双层判定均为 `completed`。 |
| Kimi M3 | 批次 `20261125T143001-4f916440`，模型 `kimi-k3.1-pro`，冻结采样 `{"temperature":1}`：4/4 完成、4/4 观察到达；`langgraph_m3_empty_continuation` 为框架 `completed`、模型 `contract_violation`，其余三项双层 `completed`。该发现按原判定保留。 |
| MiniMax M3 | 批次 `20261125T143230-c250d863`，模型 `MiniMax-M3.1-Flash`，冻结采样 `{"temperature":0.0}`：4/4 完成、4/4 观察到达，四项双层判定均为 `completed`；模型自述中的额外探针副作用也保留在原始轨迹中。 |
| 真实修改建议 | DeepSeek、Kimi、MiniMax 均已在各自批次的 `langgraph_m3_error_continuation` 上生成并持久化建议，内容包含问题证据和回归测试；建议不参与 Oracle。 |
| MySQL | 本机 `mysql80` 实机连接与独立 `faultlattice` 数据库索引重建成功；核对为 4 行、4 个唯一 `run_id`。 |
| 真实 embedding | 硅基流动 `BAAI/bge-m3` 实际返回 2 个 1024 维向量，数值均有限且非零。 |
| LanceDB | 使用四个完整 Kimi run 重建真实索引成功；真实 cosine 查询返回 4 条结果，第一条为 `20261125T143002-c4adae6c`，score 为 `0.648102`。 |

建议采样与 M3 冻结采样显式分层：通用 `_SAMPLING_PARAMS` 同时作为两者的覆盖，`_ADVISOR_SAMPLING_PARAMS` 只作用于建议。Kimi 与 MiniMax 的本机建议请求显式使用较低推理深度但保留思考，不把建议参数写入 M3 任务。缺少四件套的历史失败目录仍按契约拒绝索引，没有删除或补造历史产物。

## 当前限制

- 本地受控宿主不支持 M3；smolagents M3 当前仅登记工具错误返回与观察错误两个场景。真实端点验收仅覆盖 DeepSeek Flash 思考模式下每场景各 1 次定性运行（套件 `20261126T134221-80425144`），其他模型、故障和样本规模未覆盖；
- 单次或小样本模型运行只作定性案例分析，达到任务预注册的 `min_evaluable` 前不输出稳定比例；
- 本地宿主不支持 observation 注入（无独立 observation 通道，预检显式报错）；
- 本地同步工具支持显式 `timeout_mode=process` 的真实硬终止，smolagents／LangGraph 尚不支持该模式；默认模拟超时仍不代表真实硬终止。进程模式只终止并回收当前 worker，不保证清理其后代进程，也不是不可信代码安全沙箱。

## 批次运行与复算

```bash
# 所有任务先通过 A/B 预检，再开始执行；报告默认写入 runs/batch-report.md
faultlattice run-batch tasks/a.yaml tasks/b.yaml

# 也可只从已有原始产物重建报告
faultlattice batch-report runs/<run-a> runs/<run-b> --output reports/batch-report.md
faultlattice batch-verify runs/<run-a> runs/<run-b> --report reports/batch-report.md
```

## 索引、相似检索与回归门禁

```bash
# 按需安装可选依赖；MySQL 需预先准备空数据库和账号，命令不会启动数据库。
uv sync --group mysql --group similarity
faultlattice index-runs --runs-root runs

# embedding 仅读取硅基流动配置；模型契约变化时需使用新的索引目录。
faultlattice similarity-build --runs-root runs --index-root runs/_index/lancedb
faultlattice similarity-search "工具错误返回后仍声称成功" --limit 5

# 对公开样例执行真实四件套复算和 baseline/current 配对门禁。
faultlattice quality-gate runs/_sample/20261124T124335-94ebab0a \
  --baseline quality/public-sample.yaml --output reports/quality-gate.md

# 外部 Agent M0 门禁：两个故障坐标 + 两个无故障对照坐标。
faultlattice quality-gate \
  runs/_sample/20261127T131928-4a109d3f \
  runs/_sample/20261126T175052-1730a492 \
  runs/_sample/20261127T131958-b5e13aff \
  runs/_sample/20261126T180523-058c206a \
  --baseline quality/external-agent-m0.yaml \
  --output reports/external-agent-quality-gate.md
```

相似结果的 `score` 是 cosine similarity，不是成功率。质量门禁拒绝新增沉默失败、违反契约、注入失败、可判定样本丢失、产物缺失与复算失败；它是回归检查，不替代 pytest、Ruff 或 Pyright。外部门禁还逐层比较无故障判定是否变化，但无故障运行不进入要求实际注入的 `evaluable` 分母，也不因此获得稳定比例结论。

Ruff 的 E / F / I / UP / B 规则与 110 字符行宽保持不变。最终 CI 验收明确排除 `.verify/` 临时验收资料和 `external_projects/` 外部项目源码副本，两个目录也由 Git 忽略；`external_agents/` 中实际接入的适配器仍在检查范围内。该排除只界定项目责任边界，不表示外部项目源码已经通过 FaultLattice 的静态检查。

## 文档入口

- 规范：[docs/spec-v0.1.md](docs/spec-v0.1.md)
- 命名登记：[docs/NAMING.md](docs/NAMING.md)
- 实验操作指南：[docs/experiment-guide.md](docs/experiment-guide.md)
- 公开报告索引：[reports/README.md](reports/README.md)

## 公开样例

[runs/_sample/20261124T124335-94ebab0a](runs/_sample/20261124T124335-94ebab0a) 是一次完整的 M0 运行四件套（`tool_args / invalid_args / raise_exception`，框架层判定 `explicit_failure`）。可直接复算：

```bash
faultlattice verify runs/_sample/20261124T124335-94ebab0a
```
