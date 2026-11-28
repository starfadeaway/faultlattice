# FaultLattice 公开报告索引

本目录存放经过整理、有上下文和结论的实验报告，可随仓库公开。`runs/` 下的原始运行产物默认不公开，仅保留完整脱敏样例（`runs/_sample/`）。

## 报告清单

| 日期 | 报告 | 被测宿主及版本 | 一句话结论 | 链接 |
|---|---|---|---|---|
| 2026-11-28 | 两份模型互评的事实核验与修复答复 | FaultLattice 当前工作区 | 核心 Oracle、M3 声明协议、独立 CI、报告完整性、小样本与安全边界已修；历史结论不回改，受影响实验须按新契约重跑。 | [修复答复](external/2026-11-28-peer-review-response.md) |
| 2026-11-27 | Anchorline 真实 Embedding 与 LanceDB 索引验收 | Anchorline 0.1.0 / BAAI-bge-m3 / LanceDB | 修复适配器配置与索引目录映射后，生产写入生成 1 条 1024 维有效向量，现场查询首位命中同一事实；仅为小样本功能验收。 | [验收报告](external/2026-11-27-anchorline-vector-index-acceptance.md) |
| 2026-11-27 | Anchorline 工具结果呈现方式配对 A/B（旧口径） | Anchorline 0.1.0 | 两臂均真实写入并向调用方报失败；旧 Oracle 均记为 `contract_violation`，与新预注册失败信号口径不一致，旧零差值不作行为结论，须重跑。 | [配对报告](external/2026-11-27-anchorline-memory-result-surface-ab.md) |
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
