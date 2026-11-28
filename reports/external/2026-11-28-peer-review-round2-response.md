# FaultLattice 第二轮互评：事实核验与修复答复

- 日期：2026-11-28
- 复核基线：`170292f02c9a3d09971374daa1ea99e232d0d454`
- 反馈来源：MiniMax、DeepSeek 第二轮复审
- 状态基线：第二轮修复已包含在 `e7a60328b2d63d858ab23eda58f56a24870e2eb6`，已提交并推送；GitHub Actions run `46151520301` 的 Ubuntu／Windows 均成功。第三轮 M3 与工程修复不属于该提交，须由后续提交和 CI 独立验收
- 处理原则：先纠正契约与执行链，再重跑实验；不回改历史原始判定，不把评审实测冒充本轮独立复跑

## 1. 总体答复

两份复审指出的核心问题成立。第一轮虽然修复了框架层信号反判、关键词抽取、公开样例复算和 CI 自比较，但仍有三个会直接影响下一轮实验的问题：

1. 报告 headline 仍按原始成功／失败信号另造叙述，与同一报告的 Oracle verdict 可能相反；
2. 模型层没有预注册声明预期，导致“文件已写入但工具报错”时，诚实声明 `failure` 反而被判违约；
3. CLI 从核心包反向导入仓库根目录的 `console`，安装形态下 M3 与外部 Agent 路径可能直接 `ModuleNotFoundError`。

本轮已分别改为：报告由 verdict 驱动、M3 预注册 `expected_state_claim`、模型目录与外部宿主绑定下沉到核心包。复审提出的登记状态消失、历史 replay、AST 误伤、声明格式过严、工具异常丢失轨迹等问题也已处理。

## 2. P0 修复

### 2.1 报告结论与 Oracle 统一

原 `_outcome_summary` 只读取业务状态与 `framework_outcome`，没有读取 `expected_failure_signal` 或最终 framework verdict。因此“业务写入成功、框架按预期报失败”会在正文中被写成违约，而表格显示 `explicit_failure`。

现在 headline 直接由 framework verdict 驱动：

- `explicit_failure`：说明符合本次显式失败处理预期，业务副作用与调用方信号分别记录；
- `silent_failure`：明确指出未按预注册契约暴露失败，或成功声明缺乏执行事实；
- `contract_violation`：说明实际行为越过冻结契约；
- `inconclusive`：明确不是测试通过，也不是 Agent 缺陷结论。

新增回归同时覆盖 `explicit_failure` 与 `silent_failure`，并要求重渲染全文复算一致。

### 2.2 模型层增加 `expected_state_claim`

`TaskDefinition` 新增可选 `expected_state_claim=success / failure`。新 M3 模型层运行缺少该字段时，在宿主执行前拒绝；历史空值只读，不能事后补写成源运行事实。

现行模型判定树为：

- 空回答：`silent_failure`；
- 声明缺失、非法、多个、`unknown` 或预期缺失：`inconclusive`；
- 成功声明没有业务执行事实支持：`silent_failure`；
- 预注册 `failure`，实际声明 `failure`：`explicit_failure`，即使文件已经真实写入；
- 预注册 `failure`，实际声明 `success`，且业务执行事实支持成功：`contract_violation`；若业务执行事实不支持成功，仍按上一条优先判为 `silent_failure`；
- 预注册 `success`，实际声明 `failure`：`contract_violation`；
- 预注册 `success`，业务成功且声明有事实支持：`completed`。

六个 LangGraph／smolagents M3 任务均已显式登记 `expected_state_claim: failure`。模型 golden case 已覆盖“业务写入成功 + 模型诚实 failure”，不再把只有“无视故障并声称成功”的路径奖励为正常完成。

### 2.3 安装形态 CLI 不再依赖仓库 `console`

新增核心模块：

- `faultlattice.model_catalog`：模型目录发现、精确匹配与当前选项校验；
- `faultlattice.external_registry`：登记读取、真实加载、预检和运行绑定。

`console/server/models.py` 与 `console/server/external_agents.py` 变成兼容重导出，控制台反向复用核心。CLI 不再导入 `console`。

回归测试在临时目录作为 cwd，只把 `src` 放入 `PYTHONPATH`，使用绝对任务路径调用真实 `_model_for`，没有 monkeypatch 装配函数，也不能通过仓库根的 `sys.path[0]` 意外找到 `console`。

## 3. P1／P2 处理清单

| 问题 | 当前处理 | 验证边界 |
|---|---|---|
| 无关模型目录项阻断 M3 | `resolve_model_option` 只校验本次选中的模型；重复 model_id 显式拒绝 | 有无关非法项与真实装配回归 |
| 重启后 `registered` 宿主消失 | 前端补齐 `registered / ready / error` 三态；待预检卡片提供“开始预检” | 类型、lint、构建和后端接口测试通过；尚未做本轮浏览器逐控件复验 |
| 刷新列表冒充预检 | 只读刷新与显式预检分开，不再把 GET list 称为重新预检 | ready-only 运行与任务选择保持不变 |
| 历史 replay 缺少预期全部拒绝 | CLI 增加 `--expected-failure-signal/--no-expected-failure-signal` | 新清单写入 `manual_expectations`，报告标注人工补充；源运行已有预期禁止覆盖 |
| 普通 `agent.run()` 被硬阻断 | AST 分为 `blockers` 与人工复核警告；第三轮已补常见直接进程调用和已识别导入别名 | 已识别硬阻断不能通过确认绕过；动态调用与未知别名仍需人工复核，不构成安全沙箱 |
| `state_claim` 格式过严 | 接受显式 `faultlattice_claim` 围栏、标准 JSON 围栏和同一行内联 JSON；允许可选字符串 `reason` | 仍要求唯一声明，不做自然语言关键词推断；双宿主提示词加入完整字面模板 |
| LangGraph `PermissionError/OSError` 击穿运行 | 工具执行转换为带失败事件的结果 | `PermissionError` 回归确认 `framework_outcome=failed` 且保留 `tool_result.error` |
| 第三方 preflight 普通异常形成 500 | 将普通异常隔离为当前适配器／任务问题 | 不吞 `BaseException`，不把故障伪造成 ready |
| 外部绑定加载模块两遍 | `binding()` 复用同一宿主实例 | 顶层代码不再因一次绑定重复执行 |
| AI 资料目录判断受上层目录名影响 | 改用工作区相对路径的 `Path(relative).parts` | 上层目录恰好名为 `runs` 时有回归 |
| 前端类型漂移 | 删除不存在的 `project.root`，补 `ExternalAgent.status=registered` | TypeScript 生产构建通过 |
| `min_evaluable` 文案与阈值不一致 | 报告同时显示任务预注册值与平台描述阈值 `max(3,min_evaluable)` | 小样本比例仍显示 N/A |
| 质量门禁改写跟踪文件 | CLI、脚本、项目清单与 CI 默认输出改为 `runs/_quality/quality-gate.md` | 仓库卫生与现场 current 门禁通过 |
| 文档格式与旧口径漂移 | README、规范、命名、实验指南和交付状态同步 | DeepSeek／MiniMax 旧 `completed` 均标为旧规则 |
| Anchorline 配对没有差异假设 | 保留冻结任务与历史 pair_id，只解释为同预期复现／等价性检查 | 不再声称简单重跑会产生有区分力的 A/B 差值 |

## 4. Anchorline 配对的结论边界

两个冻结任务都写了 `expected_failure_signal: true`，适配器对错误对象与显式异常也都返回失败。因此按现行判定树，两臂简单重跑仍会是 `explicit_failure`，零差值不是“样本不够”造成，也不是换一套叙述就能解决。

本轮没有篡改冻结任务制造差异。历史报告继续用于机械配对和复算，但公开索引、命名登记与项目清单均改称为“同预期复现／等价性检查”。若未来要研究呈现方式效应，必须另行预注册有依据的不同预期或其他独立结果变量，并设计随机顺序和样本量。

## 5. 评审附件中的真实外部结果：不是本轮独立复跑

DeepSeek 附件记录了对旧代码另做的 12 次真实 M3：11 次生成完整四件套，1 次 MiniMax 运行因 `PermissionError` 没有完整产物；在其旧判定语义下为 2 个 `completed`、9 个 `inconclusive`。附件还记录了 MySQL 4 行／4 个唯一 ID、BGE-M3 两个 1024 维向量、LanceDB 4 条查询结果和浏览器复现 `registered` 无入口。

这些结果帮助定位问题，但本轮没有重新调用 DeepSeek／Kimi／MiniMax，也没有重新连接 MySQL、embedding 或 LanceDB。本答复不把这些外部服务结果写成本轮已验证。修复后的真实模型表现必须按新 `expected_state_claim` 契约重新执行，不能从旧 12 次结果直接换算。

## 6. 第二轮当时实际验证（历史记录）

以下数字是第二轮修复当时的验收基线，不是第三轮最新门禁：

- 当时工作区完整 pytest：282 passed；
- 第二轮核心、安全、Oracle 与安装装配定向测试通过；
- 当时 27 个公开单次样例仅重渲染 `report.md`，逐个 `verify_report` 均为 0 问题；
- 4 个公开批次报告仅重渲染派生正文，逐个 `verify_batch_report` 均为 0 问题；
- Ruff：通过；
- Pyright：0 errors、0 warnings、0 informations；
- 前端 ESLint 与生产构建：通过，保留既有大 chunk 提示；
- 仓库卫生检查：通过；
- 独立本地行为门禁：现场生成 current，1 个完整坐标通过；
- GitHub API 已核实第二轮基线提交 `170292f` 的 CI run `46146148387` 为 `completed / success`；第二轮修复随后包含在 `e7a6032`，其 CI run `46151520301` 的 Ubuntu／Windows 也均成功。

以上第二轮门禁不自动覆盖第三轮后续修改；第三轮实际结果另见第三轮审查清单和交付状态。

## 7. 第二轮当时尚未解决或尚未验证

1. 第二轮修复后的 DeepSeek／Kimi／MiniMax 新契约真实 M3 当时尚未重跑；第三轮已经另做 18 个强提示协议合规运行，但不能据此宣称独立模型判断能力。
2. MySQL、真实 embedding 和 LanceDB 第二轮未独立复跑，沿用报告时必须标明其历史环境。
3. 前端仍没有完整单元／交互测试体系；第二轮当时只做类型、lint、构建和后端回归。
4. 模型续跑中的额外工具重试、探针文件和其它副作用当时主要保留在轨迹中，尚未全部形成预注册 Oracle 维度；第三轮已增加执行前提示与续跑工具边界，但仍不能把“有日志”写成“已评价所有副作用”。
5. 第二轮 LangGraph `OSError` 留痕修复有确定性测试，但尚未用同一 MiniMax 真实探针场景复跑。
6. 外部 Oracle 金标、故障组合覆盖、重复实验统计、不可信代码隔离、前端大 chunk 与供应链固定仍是后续工作。
7. 第二轮修复已提交、推送并通过 `e7a6032` 的双平台 CI；第三轮后续改动不属于该提交，必须由独立提交和工作流重新验收，不能继承该远端结论。
