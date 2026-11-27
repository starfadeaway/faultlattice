# FaultLattice 公开报告索引

本目录存放经过整理、有上下文和结论的实验报告，可随仓库公开。`runs/` 下的原始运行产物默认不公开，仅保留完整脱敏样例（`runs/_sample/`）。

## 报告清单

| 日期 | 报告 | 被测宿主及版本 | 一句话结论 | 链接 |
|---|---|---|---|---|
| 2026-11-27 | Anchorline 工具结果呈现方式配对 A/B | Anchorline 0.1.0 | 首组预注册 `return_value / raise_exception` 配对均真实写入并向调用方报失败，Oracle 均为 `contract_violation`；每组一次，只作定性描述。 | [配对报告](external/2026-11-27-anchorline-memory-result-surface-ab.md) |
| 2026-11-27 | Anchorline 与 LoreKeeper 外部 Agent M0 接入验收 | Anchorline 0.1.0 / LoreKeeper 源码快照 | 两个项目各完成一次无故障对照和一次故障实验，四次均复算一致；Anchorline 故障场景出现“写入成功但报告失败”，LoreKeeper 明确记录参数故障；均为单次 M0 定性证据，不作真实模型或稳定比例结论。 | [验收报告](external/2026-11-27-anchorline-lorekeeper-m0-acceptance.md) |
| 2026-11-26 | MySQL、真实 Embedding 与 LanceDB 外部依赖验收 | PyMySQL 1.2.4 / BAAI-bge-m3 / LanceDB 0.41.0 | 4 个公开输入复算一致；MySQL 4 行且 ID 唯一，真实向量 2×1024 维，cosine 查询返回 4 条；仅作小样本功能验收。 | [验收报告](external/2026-11-26-external-dependency-acceptance.md) |
| 2026-11-25 | LangGraph M3 真实模型反事实续跑验收 | LangGraph 1.2.24 | 三个模型共 12 个单次小样本运行均完成；Kimi 空返回案例保留一项模型层 `contract_violation`，不输出稳定比例。 | [汇总报告](external/2026-11-25-langgraph-m3-real-model-acceptance.md) |
| 2026-11-25 | DeepSeek M3 批次复算 | LangGraph 1.2.24 / deepseek-flash | 4 个运行均完成且双层判定为 `completed`；每个坐标仅一次，沉默失败率为 N/A。 | [批次报告](external/2026-11-25-deepseek-m3-batch.md) |
| 2026-11-25 | Kimi M3 批次复算 | LangGraph 1.2.24 / kimi-k3.1-pro | 4 个运行均完成；空返回案例模型层为 `contract_violation`，其余为 `completed`。 | [批次报告](external/2026-11-25-kimi-m3-batch.md) |
| 2026-11-25 | MiniMax M3 批次复算 | LangGraph 1.2.24 / MiniMax-M3.1-Flash | 4 个运行均完成且双层判定为 `completed`；额外探针自述保留在公开轨迹中。 | [批次报告](external/2026-11-25-minimax-m3-batch.md) |

新报告入库时必须登记日期、报告名、被测宿主及版本、一句话结论和链接。

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
