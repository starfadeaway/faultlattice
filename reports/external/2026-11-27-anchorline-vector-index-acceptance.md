# Anchorline 真实 Embedding 与 LanceDB 索引验收

## 1. 这次解决了什么

FaultLattice 自身的真实 embedding 与 LanceDB 检索已在 2026-11-26 完成验收。本次补的是另一条链路：**Anchorline 生产 `memory_write` 写入事实后，同步生成向量、写入它自己的 LanceDB `facts_index` 表，并能现场检索到同一事实。**

此前 Anchorline 配对 A/B 的 MySQL 写入与 Oracle 结论有效，但向量索引按原项目策略降级。本次修复不改变那两次历史运行、不反向修改其四件套，也不把新的验收结果冒充为历史实验已经具备的证据。

最终结论：**修复后的 Anchorline 适配器已完成真实 BGE-M3 调用、1024 维向量落库和现场检索；验收通过。**

## 2. 根因与修复

| 问题 | 实际原因 | 修复方式 |
|---|---|---|
| Anchorline 没有使用 FaultLattice 已配置的向量服务 | 两边环境变量名称不同，适配器没有显式桥接 | 将 `FAULTLATTICE_LLM_SILICONFLOW_*` 映射为 Anchorline 的 `SILICONFLOW_*`，并要求显式声明 `embedding` 能力 |
| 验收索引可能写入非预期目录 | 适配器只设置了 `LANCEDB_URI`，而 Anchorline 的实际存储入口读取 `ANCHORLINE_LANCEDB` | 两个变量同时固定到工作区 `.verify/anchorline-lancedb` |
| 工具成功容易被误当成索引成功 | 原项目的 `upsert_fact` 失败时返回 `False`，但保留 MySQL 写入 | 验收直接读取 LanceDB 行并执行现场查询，不依赖工具成功信号或“没有报错” |

凭据只在当前后端进程中映射，不写回配置文件，不进入运行产物或本报告。模型仍冻结为 `BAAI/bge-m3`；提供了部分向量配置但字段不完整，或试图替换模型时会明确拒绝，不静默换模型。完全未提供向量配置时仍可执行只验收 MySQL 的任务，但不得据此宣称向量索引通过。

## 3. 可复用验收方式

前置条件：本机 `.env` 具有完整硅基流动 embedding 配置、独立 Anchorline 测试数据库可用、工作区内存在 Anchorline 源码副本及已安装依赖。

```bash
uv run python scripts/accept_anchorline_vector.py
```

脚本调用真实生产工具，而不是伪造向量或直接构造一条索引记录。它依次核验：

1. `memory_write` 正常完成，MySQL 新会话能读取本次事实；
2. LanceDB 中恰好存在一条与该事实 ID 对应的记录；
3. 向量为 1024 维，所有数值有限，L2 范数非零；
4. 索引中的实体、属性和值与写入内容一致；
5. 使用同一真实 embedding 配置进行现场查询，首位结果指向同一事实。

结果摘要写入本地 `.verify/anchorline-vector-acceptance-result.json`；该目录不会公开。脚本输出不包含 API Key、数据库密码或本机绝对路径。

## 4. 最终实测结果

| 核对项 | 实际结果 |
|---|---|
| 被测宿主 | Anchorline 0.1.0 工作区源码副本 |
| 真实 embedding 模型 | `BAAI/bge-m3` |
| 本次事实 ID | `2cd05674ad0e4576b2803851bc761d6e` |
| 生产工具与 MySQL 当前值 | 完成；独立会话读取一致 |
| 对应 LanceDB 记录 | 恰好 1 条 |
| 向量维度 | 1024 |
| 数值有效性 | 全部有限，范数非零 |
| 现场检索 | 首位命中同一事实 ID |
| 索引位置 | 工作区 `.verify/anchorline-lancedb` |

本次只使用专用键 `faultlattice.acceptance.vector / anchorline_bge_m3_lancedb`。验收结束后通过生产 `FactStore.forget` 失效当前值，并用 `facts_index.delete_fact` 删除对应向量；MySQL 历史记录保留，其它实体不受影响。

## 5. 回归结果

- 新增适配器环境映射与错误目录防护测试；相关外部适配器测试为 7 项通过。
- 完整测试共 **236 项通过**。
- Ruff 全部通过；Pyright 为 0 errors、0 warnings。
- 仓库卫生检查通过；公开样例门禁通过 1 个完整坐标，外部 Agent 门禁通过 6 个完整坐标。
- 运行中的后端无需重启即可重新加载适配器；Anchorline 状态为 `ready`，兼容任务为 4 项。

## 6. 边界与限制

- 这是一次小样本功能连通性验收，不证明检索相关性、向量质量、并发性能或服务稳定性。
- Anchorline 原项目的 `search_vector` 使用其既有 L2 检索与分数口径；本次只核对事实 ID 命中，不把该分数解释为 FaultLattice 的 cosine similarity、成功率或实验置信度。
- 本次没有新增或修改实验 Oracle，也没有评价真实模型推理能力。既有 A/B 的样本门禁、`contract_violation` 判定和 `validation=unvalidated` 状态保持不变。
- 真实服务仍依赖本机凭据、账号额度和网络。公开克隆若没有私有源码副本与配置，不能直接复现实机结果。
- 未修改 Anchorline 原项目源码，也未向外部项目提交 issue 或 PR。
