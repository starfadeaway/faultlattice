# Anchorline 工具结果呈现方式配对 A/B

## 1. 本次回答的问题

在 Anchorline 0.1.0 的真实 `memory_write` 边界上，同一种 `error_response` 分别作为普通返回值（A）和显式异常（B）呈现时，生产写入、调用方信号和 Oracle 判定是否出现可观察差异。

两份任务在运行前一起通过 `validate_ab_tasks`：相同 `task_id=anchorline-memory-result-ab`、相同 `pair_id=anchorline-memory-result-surface-v1`，相同脚本、后置条件、Oracle、采样门禁和适配器；唯一允许的差异是 `surface_as`。本次不是把历史单跑事后补成配对，也没有修改 Anchorline 项目源码。

## 2. 实际结果

| 组别 | 呈现方式 | 运行 ID | 新事实 ID | 真实业务状态 | 调用方信号 | 框架层 Oracle |
|---|---|---|---|---|---|---|
| A | `return_value` | `20261127T145247-77cdae58` | `9772117f57f243f7ae6fac8431759989` | 新会话确认预注册事实已写入且值一致 | `failed`；错误对象进入工具结果 | `contract_violation` |
| B | `raise_exception` | `20261127T145248-20a065b6` | `4440aae6638a4920b267cd2c0bde13e2` | 新会话确认预注册事实已写入且值一致 | `failed`；记录注入的 `RuntimeError` | `contract_violation` |

两组均满足“真实写入已提交”，同时向调用方暴露失败。按当前预注册契约，“业务任务已成功但框架报告失败”属于违反契约，而不是正常完成或沉默失败。**这一组单样本没有观察到 A/B 判定差异，但不能据此证明两种呈现方式在其他任务、版本或并发条件下始终等价。**

## 3. 为什么第二组不是重复利用第一组结果

Anchorline 会对同一实体、属性和相同当前值做幂等去重。为避免顺序污染，每组开始前只对专用键 `faultlattice.acceptance.ab / anchorline_memory_result_surface` 做夹具复位：若存在旧当前值，则通过生产 `FactStore.forget` 将其标记失效并提交；历史记录保留，不物理删除，也不触碰其它实体。

A 组开始前没有旧当前值；B 组开始前失效了 A 组事实。随后两组得到不同事实 ID，且每组 Oracle 都用全新数据库会话确认当前值，因此 B 组不是复用 A 组的当前记录。夹具复位属于执行前环境准备，不在故障注入后修改证据。

## 4. 样本门禁与复算

每组目前只有 1 次运行，预注册 `min_evaluable=2`。两次均为有效注入、证据充分且可判定，但沉默失败率和 B−A 差值保持 **N/A**。下表中的 Oracle 覆盖率 `1/1` 只描述本次原始证据完整性，不是稳定覆盖率结论；这里不输出任何外推比例。

- [A 组人读报告与四件套](../../runs/_sample/20261127T145247-77cdae58/report.md)
- [B 组人读报告与四件套](../../runs/_sample/20261127T145248-20a065b6/report.md)

公开副本仅把 `run_dir` 改为相对的 `runs/_sample/<run_id>`，不修改任务、轨迹、Oracle 或单次报告；原始运行逐字节保持不变。以下命令可在仓库根目录独立复算：

```bash
uv run faultlattice verify runs/_sample/20261127T145247-77cdae58
uv run faultlattice verify runs/_sample/20261127T145248-20a065b6
uv run faultlattice batch-verify runs/_sample/20261127T145247-77cdae58 runs/_sample/20261127T145248-20a065b6 --report reports/external/2026-11-27-anchorline-memory-result-surface-ab.md
```

## 5. 环境与限制

- 执行基于 FaultLattice 提交 `a94e2be8a1cd242b3090793e86a6e20db82d1c68`，两组适配器 SHA-256 均为 `eb5df71d28b26e9d089cee121bfd5b90a8f3d45dd2b81fe4f235bc97066ed310`，依赖锁哈希一致。
- 本实验为 M0 预设脚本，`model_invoked=false`，没有调用真实模型，不评价模型推理或自我修正能力。
- Oracle 为确定性状态读取，但 `validation=unvalidated`；尚未完成该配对场景的黄金样例或人工对齐验证。
- 直连执行脚本没有把 FaultLattice 的硅基流动配置映射为 Anchorline 原项目变量，因此两次向量索引均按 Anchorline 既有策略记录“保留 MySQL、跳过索引”的降级警告。本次只验收生产写入与工具结果边界，**不宣称向量索引通过验收**；该警告不改变上述 MySQL 后置证据。
- 本报告不包含数据库凭据、API Key 或本机绝对路径。下面的机器指标块只用于独立复算，不是另一套实验结论。

## 6. 批次聚合与机器复算锚点


## 阅读摘要

- 本批次包含 **2 次真实运行**、**2 个分层实验条件**、**1 个 A/B 配对**。
- “总运行数”是 Harness 执行并落盘的数量，不是 Agent 通过数；“可判定”是 Oracle 证据足够的数量，也不等于行为正确。
- 每个坐标的沉默失败率只有在可判定数达到预注册 `min_evaluable`，且证据不足未超过阈值时才展示；否则为 **N/A**。A/B 不合并平均。
- 具体行为结论应回到对应 run 的人读报告；本页负责同坐标聚合和复算，不用一个百分比替代原始轨迹。

## 分层指标主表

`framework` 为框架层，`model` 为模型层；故障条件依次是“注入点 / 故障类型 / 呈现方式”。“门禁”说明比例被隐藏的原因，不是 Harness 错误。

| 实验单元 | 宿主 × 模式 | 故障条件 | 评价层 | 总运行数 | 注入失败 | 适用集 | 可判定 | 沉默失败次数 | 沉默失败率 | Oracle 覆盖率 | 证据不足 | 不适用原因计数 | 比例门禁 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| anchorline-memory-result-ab | anchorline × M0 | tool_result / error_response / raise_exception | 框架层 | 1 | 0 | 1/1（100.00%） | 1 | 0 | N/A | 100.00% | 0（0.00%） | — | 低于预注册最低样本数 |
| anchorline-memory-result-ab | anchorline × M0 | tool_result / error_response / return_value | 框架层 | 1 | 0 | 1/1（100.00%） | 1 | 0 | N/A | 100.00% | 0（0.00%） | — | 低于预注册最低样本数 |


## A/B 对照


### anchorline-memory-result-surface-v1

| 层 | 组别 | surface_as | 样本数 | 可判定数 | 沉默失败次数 | 沉默失败率 |
|---|---|---|---:|---:|---:|---:|
| framework | A | return_value | 1 | 1 | 0 | N/A |
| framework | B | raise_exception | 1 | 1 | 0 | N/A |


- 框架层沉默失败率差值（B − A）：N/A。
- 模型层沉默失败率差值（B − A）：N/A。


## 完整分层明细

下表用于定位原始四件套。`injection_applied=True` 只表示故障确实生效；`observation_status` 只表示故障是否进入模型观察，两者都不是“测试通过”。

| run_id | 任务 | 宿主 × 模式 | 族 | 注入点 | 故障类型 | surface_as | 注入生效 | observation_status |
|---|---|---|---|---|---|---|---|---|
| 20261127T145247-77cdae58 | anchorline-memory-result-ab | anchorline × M0 | tool_fault | tool_result | error_response | return_value | True | not_applicable |
| 20261127T145248-20a065b6 | anchorline-memory-result-ab | anchorline × M0 | tool_fault | tool_result | error_response | raise_exception | True | not_applicable |


<details>
<summary>查看机器复算锚点（供 batch-verify 逐字核对）</summary>

以下 JSON 是完整机器指标，不是另一套实验结论。`faultlattice batch-verify` 会从上述原始运行独立重算并逐字比较。

```json faultlattice-batch-metrics
{"groups":[{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"raise_exception","target_layers":["framework"],"task_fingerprint":"b25cdb0af347246290bae33b2a95678b2adcbeef340bb450d75b6de44de1445e","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145248-20a065b6"]},{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"return_value","target_layers":["framework"],"task_fingerprint":"ffd00db8400209519369ea38bd1f6e5b4b3b87ce096071edce4cb97456979014","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145247-77cdae58"]}],"pairs":[{"a":{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"return_value","target_layers":["framework"],"task_fingerprint":"ffd00db8400209519369ea38bd1f6e5b4b3b87ce096071edce4cb97456979014","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145247-77cdae58"]},"b":{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"raise_exception","target_layers":["framework"],"task_fingerprint":"b25cdb0af347246290bae33b2a95678b2adcbeef340bb450d75b6de44de1445e","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145248-20a065b6"]},"framework_rate_difference":null,"model_rate_difference":null,"pair_id":"anchorline-memory-result-surface-v1"}],"run_ids":["20261127T145247-77cdae58","20261127T145248-20a065b6"],"runs":[{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_applied":true,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","observation_status":"not_applicable","run_dir":"runs/_sample/20261127T145247-77cdae58","run_id":"20261127T145247-77cdae58","surface_as":"return_value","target_layers":["framework"],"task_fingerprint":"ffd00db8400209519369ea38bd1f6e5b4b3b87ce096071edce4cb97456979014","task_id":"anchorline-memory-result-ab"},{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_applied":true,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","observation_status":"not_applicable","run_dir":"runs/_sample/20261127T145248-20a065b6","run_id":"20261127T145248-20a065b6","surface_as":"raise_exception","target_layers":["framework"],"task_fingerprint":"b25cdb0af347246290bae33b2a95678b2adcbeef340bb450d75b6de44de1445e","task_id":"anchorline-memory-result-ab"}],"schema_version":1,"total_runs":2}
```

</details>
