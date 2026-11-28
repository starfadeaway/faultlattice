# FaultLattice 公开报告索引

本目录存放经过整理、有上下文和结论的实验报告，可随仓库公开。`runs/` 下的原始运行产物默认不公开，仅保留完整脱敏样例（`runs/_sample/`）。

## 报告清单

| 日期 | 报告 | 被测宿主及版本 | 一句话结论 | 链接 |
|---|---|---|---|---|
| 2026-11-29 | 第四轮模型审查事实核对与修复记录 | FaultLattice / LangGraph 可控回归 | 修复 Harness 异常时阻断证据丢失，增加失败清单与部分轨迹；补齐截断预注册限制、声明缺失原因码及历史报告解释边界。 | [第四轮处置](external/2026-11-29-fourth-round-review-triage.md) |
| 2026-11-28 | 首轮易错点契约 M3 三模型重跑验收 | LangGraph 1.2.24 / smolagents / 三模型 | 新冻结 18 个坐标全部完成并公开复算，全部使用标准 JSON 且只有一次目标写入；结论限于强提示协议合规，不证明独立故障判断。 | [首轮契约重跑](external/2026-11-28-m3-precall-contract-rerun.md) |
| 2026-11-28 | 第三轮模型审查事实核对与处理顺序 | FaultLattice 当前工作区 | 核实提示词预期泄露、任务文本与 unknown 语义、上传白名单、AST、预检选择及 63 份私有旧报告；区分当前问题与过时状态。 | [第三轮审查清单](external/2026-11-28-third-round-review-triage.md) |
| 2026-11-28 | 新结构化声明契约 M3 真实模型补跑验收 | LangGraph 1.2.24 / smolagents / 三模型 | 18 个冻结坐标中 14 个完成并公开复算，11 个显式失败、3 个证据不足、4 个 Harness 错误；额外写入与声明格式变体单独留痕，不作模型排名。 | [补跑验收](external/2026-11-28-m3-new-contract-rerun.md) |
| 2026-11-28 | 第二轮模型互评的事实核验与修复答复 | FaultLattice 当前工作区 | 修复报告叙述、模型预期反判、安装形态 CLI、历史 replay、登记状态与草案误伤；评审中的真实外部结果与本轮独立测试分开记录。 | [第二轮答复](external/2026-11-28-peer-review-round2-response.md) |
| 2026-11-28 | 两份模型互评的事实核验与修复答复 | FaultLattice 当前工作区 | 核心 Oracle、M3 声明协议、独立 CI、报告完整性、小样本与安全边界已修；历史结论不回改，受影响实验须按新契约重跑。 | [修复答复](external/2026-11-28-peer-review-response.md) |
| 2026-11-27 | Anchorline 真实 Embedding 与 LanceDB 索引验收 | Anchorline 0.1.0 / BAAI-bge-m3 / LanceDB | 修复适配器配置与索引目录映射后，生产写入生成 1 条 1024 维有效向量，现场查询首位命中同一事实；仅为小样本功能验收。 | [验收报告](external/2026-11-27-anchorline-vector-index-acceptance.md) |
| 2026-11-27 | Anchorline 工具结果呈现方式同预期复现（历史 pair_id／旧口径） | Anchorline 0.1.0 | 两臂均预期并实际报失败，没有相反的 verdict 假设；历史机械配对与零差值只作等价性检查，不再把简单重跑当作有行为区分力的 A/B。 | [历史配对报告](external/2026-11-27-anchorline-memory-result-surface-ab.md) |
| 2026-11-27 | Anchorline 与 LoreKeeper 外部 Agent M0 接入验收（旧口径） | Anchorline 0.1.0 / LoreKeeper 源码快照 | 四次均保留真实执行事实并复算一致；Anchorline 的旧 `contract_violation` 不作为新契约结论，LoreKeeper 明确记录参数故障；均为单次 M0 定性证据。 | [验收报告](external/2026-11-27-anchorline-lorekeeper-m0-acceptance.md) |
| 2026-11-26 | MySQL、真实 Embedding 与 LanceDB 外部依赖验收 | PyMySQL 1.2.4 / BAAI-bge-m3 / LanceDB 0.41.0 | 4 个公开输入复算一致；MySQL 4 行且 ID 唯一，真实向量 2×1024 维，cosine 查询返回 4 条；仅作小样本功能验收。 | [验收报告](external/2026-11-26-external-dependency-acceptance.md) |
| 2026-11-25 | LangGraph M3 真实模型反事实续跑验收（旧模型规则） | LangGraph 1.2.24 | 12 个运行保留真实调用与观察事实；旧模型层 verdict 不作新结构声明契约下的行为结论，Kimi 空返回项是关键词假阳性案例，全部需按新协议重跑。 | [汇总报告](external/2026-11-25-langgraph-m3-real-model-acceptance.md) |
| 2026-11-25 | DeepSeek M3 批次复算（旧模型规则） | LangGraph 1.2.24 / deepseek-flash | 4 个运行均完成；旧双层判定只作审计记录，每个坐标一次且沉默失败率为 N/A，新行为结论需重跑。 | [批次报告](external/2026-11-25-deepseek-m3-batch.md) |
| 2026-11-25 | Kimi M3 批次复算（旧模型规则） | LangGraph 1.2.24 / kimi-k3.1-pro | 4 个运行均完成；空返回案例的旧 `contract_violation` 是否定句关键词误判，不作为模型违约证据。 | [批次报告](external/2026-11-25-kimi-m3-batch.md) |
| 2026-11-25 | MiniMax M3 批次复算（旧模型规则） | LangGraph 1.2.24 / MiniMax-M3.1-Flash | 4 个运行均完成；旧 verdict 只作审计记录，额外探针自述保留在轨迹中但未被旧 Oracle 真实测量。 | [批次报告](external/2026-11-25-minimax-m3-batch.md) |

新报告入库时必须登记日期、报告名、被测宿主及版本、一句话结论和链接。

本轮确定性本地行为门禁另见 [quality-gate](quality-gate.md)。该报告由当前代码现场生成 current 后产生，不属于外部 Agent 实验报告。

## 报告要求

每份报告必须包含（模板见 [templates/experiment-report.md](templates/experiment-report.md)）：

- 被测宿主及版本；
- 实验任务与故障配置；
- 预注册预期；
- Oracle 与指标口径；
- 执行命令；
- 原始样例入口（`runs/_sample/<run_id>` 四件套）；
- 结果与限制；
- 是否发现异常，以及后续 issue / PR。

本索引与模板不预填实验数字，全部等待真实运行结果。
