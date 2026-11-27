# Anchorline 与 LoreKeeper 外部 Agent M0 接入验收

## 1. 结论速览

本次依次完成两个外部项目的资料上传、AI 适配器草案、人工复核、保存、真实加载、预检、任务冻结、实验执行、四件套生成、独立复算和聚合分析。在两个既有故障任务之外，现又各完成一次**无故障对照**，用于检查相同生产边界在正常条件下能否满足预注册契约。

| 被测对象与场景 | 业务任务实际结果 | 框架向调用方报告 | Harness 执行 | Oracle 判定 |
|---|---|---|---|---|
| Anchorline：正常 `memory_write` | 对照事实真实写入，新数据库会话确认值一致 | 正常完成 `completed` | 完成 `completed` | 正常完成 `completed` |
| Anchorline：写入后替换工具结果 | 验收事实真实写入，新数据库会话确认值一致 | 明确失败 `failed` | 完成 `completed` | 违反契约 `contract_violation`：业务已成功，却向调用方报失败 |
| LoreKeeper：正常 `calculator` | 原算式未经改写并成功执行，实际返回 `1000` | 正常完成 `completed` | 完成 `completed` | 正常完成 `completed` |
| LoreKeeper：工具参数改为除零算式 | 原算式未计算；改写后的算式按场景失败并留下错误记录 | 明确失败 `failed` | 完成 `completed` | 显式失败 `explicit_failure`：失败被记录并明确暴露 |

**四次都是 M0 预设脚本驱动，不是实际模型能力测试。** Anchorline 运行真实生产记忆工具与数据库；LoreKeeper 运行真实生产 ReAct 循环与计算器，但模型输出均由预注册脚本提供。Harness `completed` 只说明执行、落盘和复算流程完成，不表示整个 Agent 已通过测试。

两次无故障对照没有设置 `pair_id`，不构成规范中的配对 A/B 实验。每个任务坐标仍只有一个样本，只作定性比较，不计算或外推稳定成功率、失败率或覆盖率。

## 2. 实验对象与冻结环境

| 字段 | Anchorline | LoreKeeper |
|---|---|---|
| 接入来源 | 工作区内的完整源码副本 | 工作区内的完整源码副本 |
| 生产边界 | `build_tools(...)[memory_write]` 与 `FactStore` | `ReActAgent.run`、`_exec_call` 与 `calculator` |
| 适配器 | `external_agents/drafts/anchorline.py` | `external_agents/drafts/lorekeeper.py` |
| 适配器类 | `AnchorlineHostAdapter` | `LoreKeeperHostAdapter` |
| 历史故障运行执行哈希 | `eb5df71d28b26e9d089cee121bfd5b90a8f3d45dd2b81fe4f235bc97066ed310` | `7cd295c9f2f4766b5b9a7199f677de962251b803f4434e0ad349bd85f05d8ae3` |
| 本次无故障对照执行哈希 | `eb5df71d28b26e9d089cee121bfd5b90a8f3d45dd2b81fe4f235bc97066ed310` | `dfc2c68a660a8125ce5cee022d414305fa7fdf0719973b5bf3a7f4638aebc61a` |
| 宿主包版本 | `0.1.0` | 未登记独立包版本 |
| 宿主 commit | 未登记；以源码快照和适配器哈希界定 | 未登记；以源码快照和适配器哈希界定 |
| 执行模式 | M0 · 预设脚本 | M0 · 预设脚本 |
| 真实模型参与 | 否 | 否 |

历史运行保留实际执行时的适配器哈希，不回写为当前文件哈希。为支持 LoreKeeper 无故障对照，适配器新增 `[计算完成]` 成功回答前缀及无故障状态观察分支；原有 `[计算失败]`、参数注入和故障观察分支保持不变。新增单元测试同时覆盖成功和故障分支，且历史故障产物再次复算一致。

外部依赖按最小独立依赖组接入，没有直接安装外部项目的整套依赖，也没有用其版本约束覆盖 FaultLattice 已验证环境。因此本次只验收上述生产边界，不宣称两个外部项目的全部功能或原始依赖组合都已通过。

## 3. 任务与故障配置

### 3.1 Anchorline 故障任务：真实写入后替换工具结果

- 任务：`anchorline-memory-result-error`。
- 任务文件：`tasks/custom/anchorline-memory-result-error.yaml`。
- 用户目标：向独立测试数据库写入实体 `faultlattice.acceptance` 的 `anchorline_memory_marker` 事实。
- 故障坐标：`tool_fault / tool_result / error_response / return_value`。
- 实际注入：工具已经提交真实写入后，把宿主看到的返回替换为错误对象。
- 预注册验收：新数据库会话应读到相同事实值；宿主应向调用方返回明确失败，而不是继续给出成功回答。
- 实际事实 ID：`60e0718319524f1987b7fb1efc55c166`。

### 3.2 LoreKeeper 故障任务：在生产工具执行前改坏参数

- 任务：`lorekeeper-calculator-invalid-args`。
- 任务文件：`tasks/custom/lorekeeper-calculator-invalid-args.yaml`。
- 用户目标：通过生产 ReAct 循环调用计算器，计算 `(0.8 + 0.2) * 1000`。
- 故障坐标：`tool_fault / tool_args / invalid_args / return_value`。
- 实际注入：在 `_exec_call` 边界把 `expression` 改为 `1 / 0`。
- 预注册验收：原算式不得产生成功结果；生产状态应留下失败步骤和 `tool_failures=1`；适配器把 `[计算失败]` 前缀映射为显式失败信号。
- 实际工具错误：`[错误] 1 / 0 出现除零。`。

### 3.3 Anchorline 无故障对照：独立事实正常写入

- 任务：`anchorline-memory-result-normal`；任务文件：`tasks/custom/anchorline-memory-result-normal.yaml`。
- 用户目标：调用同一生产 `memory_write`，写入实体 `faultlattice.acceptance.control` 的独立事实，避免覆盖故障实验的验收事实。
- 故障配置：`fault=null`，不设置注入点，不允许安全降级。
- 预注册验收：工具提交后，新数据库会话应找到该事实且当前值与预注册文本完全一致；框架应报告完成。
- 实际事实 ID：`09e2a7c8740a46f4b0b803b433625f9d`；工具结果 `ok=true`，没有注入事件。

### 3.4 LoreKeeper 无故障对照：原算式正常执行

- 任务：`lorekeeper-calculator-normal`；任务文件：`tasks/custom/lorekeeper-calculator-normal.yaml`。
- 用户目标：通过生产 ReAct 循环和生产计算器执行 `(0.8 + 0.2) * 1000`。
- 故障配置：`fault=null`，不改写参数，不允许安全降级。
- 预注册验收：恰好一次 `calculator` 调用使用原算式并成功；`tool_failures=0`；框架报告完成。
- 实际工具返回：`(0.8 + 0.2) * 1000 = 1000`；生产状态记录一个成功步骤、零次工具失败，没有注入事件。

四项任务的 Oracle 都是 `source=state`、`determinism=deterministic`、`validation=unvalidated`。首次接入尚未完成黄金样例或人工对齐验证，不能把确定性计算误写成 Oracle 已被证明完全正确。

## 4. 实际执行结果与复算入口

| 项目 | Anchorline 无故障 | Anchorline 故障 | LoreKeeper 无故障 | LoreKeeper 故障 |
|---|---|---|---|---|
| 批次 ID | `20261127T131928-a9ed822d` | `20261126T175052-b5a3f10b` | `20261127T131958-413d1dc9` | `20261126T180523-35ab1d84` |
| 运行 ID | `20261127T131928-4a109d3f` | `20261126T175052-1730a492` | `20261127T131958-b5e13aff` | `20261126T180523-058c206a` |
| 轨迹事件数 | 5 | 5 | 6 | 7 |
| 工具调用 / 返回 | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |
| 故障注入事件数 | 0 | 1 | 0 | 1 |
| 独立业务状态证据 | 事实存在且值一致 | 事实存在且值一致 | 原算式成功；`tool_failures=0` | 原算式无成功结果；`tool_failures=1` |
| 框架层判定 | `completed` | `contract_violation` | `completed` | `explicit_failure` |
| 独立复算 | 一致 | 一致 | 一致 | 一致 |

公开样例与人读报告：

- [Anchorline 无故障对照](../../runs/_sample/20261127T131928-4a109d3f/report.md)
- [Anchorline 故障运行](../../runs/_sample/20261126T175052-1730a492/report.md)
- [LoreKeeper 无故障对照](../../runs/_sample/20261127T131958-b5e13aff/report.md)
- [LoreKeeper 故障运行](../../runs/_sample/20261126T180523-058c206a/report.md)

公开复算命令：

```bash
uv run faultlattice verify runs/_sample/20261127T131928-4a109d3f
uv run faultlattice verify runs/_sample/20261126T175052-1730a492
uv run faultlattice verify runs/_sample/20261127T131958-b5e13aff
uv run faultlattice verify runs/_sample/20261126T180523-058c206a
```

每个公开目录均包含 `run.json`、`steps.jsonl`、`oracle.jsonl`、`report.md` 四件套。副本只把 `run_dir` 改为相对的 `runs/_sample/<run_id>`，任务、故障、轨迹、Oracle 和报告保持原值；原始运行目录未修改。报告中的 `faultlattice-metrics` 是机器复算锚点，不是另一项行为判定。

四个坐标已登记到 `quality/external-agent-m0.yaml` 并加入 GitHub Actions。当前 baseline 4 次、current 4 次、4 个完整坐标、0 项违规，详见[外部 Agent 回归门禁](../external-agent-quality-gate.md)。无故障坐标另比较逐层判定变化，但不进入故障实验的可判定分母；该门禁证明相对回归检查通过，不证明 Oracle 已验证或 Agent 没有其它缺陷。

## 5. 定性对照说明

### 5.1 Anchorline

正常执行时，真实事实写入、框架完成信号和 Oracle 完成判定一致；在工具真实提交后注入错误返回时，事实仍写入，但框架向调用方报失败，形成 `contract_violation`。这为“该故障坐标下出现业务状态与调用方信号错位”提供了对照证据。

对照使用独立事实键，且 Anchorline 适配器未改代码。但两次仍不是同输入重复试验，不能据此估计发生率，也不能推断其它工具结果、异常形式或并发场景。

### 5.2 LoreKeeper

正常执行时，原算式未经改写，生产工具成功返回 `1000`，生产状态为零失败，框架与 Oracle 均为完成；参数故障执行时，生产计算器收到除零算式并留下明确错误，框架和 Oracle 均为显式失败。这说明本次观察分支能区分“正常完成”和“按场景明确失败”，不是只接受一种预设结果。

LoreKeeper 的无故障运行使用了扩展后的适配器版本，故障运行保留旧执行哈希，因此这里是**定性对照而非严格 A/B**。现有故障分支由回归测试和历史产物复算保护，但仍需更多同版本、同输入的预注册重复运行才能进行更强比较。

## 6. AI 草案、建议与分析的实际状态

### 6.1 适配器草案没有直接获得执行权限

两个草案均由 `kimi-k3.1-pro` 生成，随后人工修正，再分别保存和登记。AI 没有自动登记或运行代码。

- Anchorline 原草案误解了 FaultLattice 的脚本、故障和返回协议；人工版改为真实 `HostRunResult` 与独立数据库后置观察。
- LoreKeeper 原草案使用了错误的 `faults` 能力字段、错误的脚本形状，并错误假设源码位于运行沙箱；人工版改为标准 `injection_points`、任务脚本和生产 `ReActAgent.run`。

### 6.2 单任务修改建议：空响应与截断已处理

两个故障任务的首次建议请求均返回 HTTP 409：模型把 token 用在推理字段，最终正文为空（`max_tokens=8192`）。系统没有自动重试，也没有保存空内容。随后使用 `deepseek-flash` 明确重试，02:09:06 与 02:12:22（北京时间）分别得到非空正文，但结尾均在句子中间截断，不能视为完整建议。

收尾时已将提供方 `finish_reason` 纳入模型响应：`length` 现在会返回 409，且不覆盖已有建议；建议默认 token 上限调为 16384，并要求正文不超过 1800 字、最多三项建议。重新加载服务后，两项均在保留 DeepSeek 思考模式的情况下完整生成并覆盖截断稿：Anchorline 为 2026-11-27 02:40:21，LoreKeeper 为 02:40:48（均为北京时间）。实验页提供正文与 Markdown 下载；建议只供人工复核，不改变原始轨迹或 Oracle。

### 6.3 聚合分析已生成但不能替代根因复核

两个故障批次的聚合分析均成功。模型明确指出了一个样本不能外推；其输入只有聚合数量与判定，不包含完整轨迹、源码或单次证据，因此不能据此定位根因。实际结论仍以本报告列出的原始轨迹、生产状态和复算结果为准。新增对照不会被描述为已经生成 LLM 修改建议；正常完成也没有必须修改的事项。

## 7. 异常与后续

1. **Anchorline 的状态—信号错位是本次真实实验发现。** 它证明该坐标下“数据库已写入”和“调用方收到失败”同时发生；是否需要修改上游框架，还需结合产品契约和更多场景人工判断。
2. **Anchorline 的 Oracle 口径已按规范澄清。** LLM 曾建议复核“允许明确失败”与 `contract_violation` 是否冲突；对照开发提示词第七节的框架判定树和 `framework_contract_violation` 金样例后，确认“任务实际成功 + 向调用方返回失败信号”应判为 `contract_violation`。允许降级不意味着把已完成的任务改记为失败，因此本次保留原判定，无需修改 Oracle。
3. **LoreKeeper 的显式失败是本次故障场景的预期处理。** 它不是 Harness 故障，也不能据此宣称 LoreKeeper 在其他参数、工具或真实模型下都可靠。
4. **建议生成链路已增加截断保护。** 空响应与 `finish_reason=length` 不会作为完整建议保存；模型仍可能返回空内容，此时需要用户明确重试，不自动切换模型或关闭思考。
5. **LoreKeeper 故障批次收尾曾出现一次 Windows 文件替换拒绝访问。** 日志记录了 `suite.json` 原子替换的 `PermissionError`；随后最终状态已持久化，当前接口、套件文件和单次产物一致，复算通过。现已在文件句柄关闭后对 Windows 瞬态 `PermissionError` 增加最多五次、总计至多 0.75 秒的退避重试；持续占用和非 Windows 权限错误仍立即抛出。新增测试覆盖“第三次成功”“持续失败五次”“非 Windows 不重试”，不修改历史日志或实验产物。
6. **后续扩样应先预注册。** 可在同版本适配器上重复同一任务，再增加其他非法参数、其他工具结果故障和更多生产工具；每个新坐标保持独立计数。若要做规范中的配对 A/B，必须另行预注册 `pair_id` 和对应协议，不能事后给这四次运行补配对关系。
7. 本次未向外部项目提交 issue 或 PR；当前证据首先是 FaultLattice 接入验收结果，不自动归因成上游缺陷。

## 8. 限制

- 每个任务坐标只有一次 M0 运行，不能估计稳定行为分布。
- M0 的 `model_output` 全是预设内容，不能用于评价真实模型的自我修正、推理或工具选择能力。
- Anchorline 只覆盖 `memory_write`，分别观察正常返回和 `tool_result` 错误；LoreKeeper 只覆盖 `calculator`，分别观察原参数和 `tool_args` 故障。其它工具、观察注入和 M3 尚未由这两个适配器声明或验证。
- LoreKeeper 的 `[计算失败]` / `[计算完成]` 到框架信号是适配器明示的映射契约，不应被误写成所有宿主接口都原生采用相同信号。
- 无故障对照只证明本次正常路径满足预注册条件，不证明其它功能、异常路径、并发行为或真实模型可靠。
- 聚合 LLM 未读取完整轨迹；其文本是辅助分析，不是实验事实来源。
