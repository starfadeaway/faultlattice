# MySQL、真实 Embedding 与 LanceDB 外部依赖验收

## 1. 概述

- 初次验收：2026-11-25。
- 本次只读复核与真实查询：2026-11-26（本机 Asia/Shanghai）。
- 范围：MySQL 事务型结构索引、硅基流动真实 embedding、LanceDB 本地向量索引与 cosine 查询。
- 输入：四个完整的 Kimi × LangGraph M3 公开运行四件套。
- 一句话结论：三项外部依赖均完成真实调用或实机读写；当前 MySQL 为 4 行且 4 个唯一 `run_id`，真实向量返回 2 个 1024 维有效向量，LanceDB 查询返回 4 条记录，四个输入样例的批次复算一致。

这不是模型可靠性评测，也不是数据库或向量服务性能基准。它只证明指定本机环境、依赖版本和四个输入下的功能连通性、数据契约及可复算性。

## 2. 实际环境

| 组件 | 实际值 |
|---|---|
| MySQL 服务 | 本机既有 `mysql80` 服务；独立 `faultlattice` 数据库 |
| MySQL 表 | `faultlattice_runs`；`run_id` 为主键 |
| PyMySQL | 1.2.4 |
| Embedding 提供方 | 硅基流动 OpenAI 兼容 embeddings 端点 |
| Embedding 模型 | `BAAI/bge-m3` |
| 向量契约 | 1024 维、L2 归一化、cosine；配置版本 `bge-m3` |
| OpenAI SDK | 3.59.0；单次请求，不启用 SDK 隐式重试 |
| LanceDB | 0.41.0 |
| PyArrow | 23.0.1 |

凭据只从本机 `.env` 读取。本报告不记录用户名、密码、API key、完整本机目录或密钥派生值。MySQL 服务由用户预先准备，验收命令不会启动或停止系统服务。

## 3. 输入与事实来源

索引输入为以下四个公开目录；每个目录都包含 `run.json`、`steps.jsonl`、`oracle.jsonl` 和 `report.md`：

1. `runs/_sample/20261125T143002-c4adae6c`
2. `runs/_sample/20261125T143029-fa4d6cf0`
3. `runs/_sample/20261125T143050-afe298f3`
4. `runs/_sample/20261125T143110-9effe896`

原始四件套是唯一实验事实来源。MySQL 表和 `runs/_index/lancedb/` 都是可覆盖重建的派生数据，不得反向修改原始运行、Oracle 或报告。

本次先执行独立批次复算：

```bash
uv run faultlattice batch-verify \
  runs/_sample/20261125T143002-c4adae6c \
  runs/_sample/20261125T143029-fa4d6cf0 \
  runs/_sample/20261125T143050-afe298f3 \
  runs/_sample/20261125T143110-9effe896 \
  --report reports/external/2026-11-25-kimi-m3-batch.md
```

实际结果：`批次复算一致`。逐任务判定和指标口径见 [Kimi M3 批次复算报告](2026-11-25-kimi-m3-batch.md)。

## 4. 执行与复核命令

安装固定依赖组：

```bash
uv sync --group mysql --group similarity
```

### 4.1 MySQL 重建

原始验收时，输入目录只包含上述四个运行：

```bash
uv run faultlattice index-runs --runs-root <four-run-input>
```

该命令在单个事务中建表、删除旧派生记录并写入新记录；失败时回滚。重跑会覆盖派生表，且输入目录中的运行数变化时，输出行数也应随之变化。

本次只读核对执行：

```sql
SELECT COUNT(*), COUNT(DISTINCT run_id) FROM faultlattice_runs;
SELECT run_id FROM faultlattice_runs ORDER BY run_id;
```

### 4.2 真实 embedding 数值检查

通过 `OpenAIEmbeddingProvider.from_env()` 对以下两段文本各生成一个向量：

```text
工具错误返回后仍声称成功
空响应后虚构写入结果
```

检查返回数量、维度、所有数值有限，以及每个向量至少包含一个非零值。没有保存或公开原始向量，因为验证契约不需要把大段浮点数组写入报告。

### 4.3 LanceDB 覆盖重建与真实查询

原始构建使用同一四运行输入目录：

```bash
uv run faultlattice similarity-build \
  --runs-root <four-run-input> \
  --index-root runs/_index/lancedb
```

本次真实查询：

```bash
uv run faultlattice similarity-search "工具错误返回后仍声称成功" --limit 4
```

查询会现场调用同一 embedding 提供方，再执行真实 LanceDB cosine 检索；不是读取报告中的预填排序。

## 5. 实际结果

### 5.1 MySQL 只读回查

| 核对项 | 实际结果 |
|---|---:|
| 表内记录数 | 4 |
| 唯一 `run_id` 数 | 4 |
| 与四个输入 ID 完全一致 | 是 |

当前四个 ID 为 `20261125T143002-c4adae6c`、`20261125T143029-fa4d6cf0`、`20261125T143050-afe298f3`、`20261125T143110-9effe896`。

### 5.2 真实 embedding

| 核对项 | 实际结果 |
|---|---:|
| 返回向量数 | 2 |
| 每个向量维度 | 1024 |
| 所有数值有限 | 是 |
| 每个向量均非零 | 是 |
| 模型 ID | `BAAI/bge-m3` |

### 5.3 LanceDB 索引与查询

`runs/_index/lancedb/index-metadata.json` 当前记录 `schema_version=1`、`record_count=4`、四个相同运行 ID，以及冻结的 1024 维、L2、cosine 契约。

| 排名 | `run_id` | 宿主 / 模式 | 故障类型 / 呈现方式 | cosine similarity |
|---:|---|---|---|---:|
| 1 | `20261125T143002-c4adae6c` | langgraph / M3 | error_response / return_value | 0.648102 |
| 2 | `20261125T143050-afe298f3` | langgraph / M3 | error_response / not_applicable | 0.609536 |
| 3 | `20261125T143110-9effe896` | langgraph / M3 | malformed_content / not_applicable | 0.601596 |
| 4 | `20261125T143029-fa4d6cf0` | langgraph / M3 | empty_response / return_value | 0.600478 |

`score = 1 - cosine_distance`。它只表示查询文本与运行文本的向量相似度，不是成功率、缺陷率、实验置信度或模型排名。

## 6. 异常与后续

- 本次 LanceDB 查询出现一条非致命弃用警告：显式选择输出列时未列出 `_distance`，当前版本仍自动补上；未来版本将改变该行为。后续升级 LanceDB 时应按新 API 显式保留距离列或采用 `disable_scoring_autoprojection`，并重新运行相似检索端到端测试。
- 未向外部项目提交 issue 或 PR：当前警告来自已固定依赖的未来行为提示，尚不是本次功能失败。
- 四个公开输入复算一致，没有发现缺失四件套、重复 `run_id`、空向量、非有限值或索引记录数不一致。

## 7. 限制

- 真实服务可用性依赖本机配置和账号权限；公开报告不包含凭据，其他人复现实机调用前必须自行配置 `.env`。
- 四个运行和一次查询只证明小样本功能链路，不证明查询相关性、服务稳定性、并发性能或大规模索引表现。
- 远程 embedding 结果可能随服务端模型或数值实现变化；索引与查询必须使用相同冻结契约，历史分数不应冒充永久常量。
- 当前 LanceDB 是小规模精确检索，没有引入 IVF 等近似索引参数，也没有据此声称具备大规模性能结论。
- 本报告不新增或改变任何 Agent 行为判定；模型实验结论仍以公开四件套和对应批次报告为准。
