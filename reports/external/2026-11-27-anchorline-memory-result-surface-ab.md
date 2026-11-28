# FaultLattice 批次报告

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
{"groups":[{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"raise_exception","target_layers":["framework"],"task_fingerprint":"7209b8aaee21f1b5399ea375f711e4a30a3997a363ff9881f6eb1137260cc131","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145248-20a065b6"]},{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"return_value","target_layers":["framework"],"task_fingerprint":"5742b1fe1bf9f825535f6c468ede7cf407230707380a2c081b10748ee6e9ad56","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145247-77cdae58"]}],"pairs":[{"a":{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"return_value","target_layers":["framework"],"task_fingerprint":"5742b1fe1bf9f825535f6c468ede7cf407230707380a2c081b10748ee6e9ad56","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145247-77cdae58"]},"b":{"conditions":{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","surface_as":"raise_exception","target_layers":["framework"],"task_fingerprint":"7209b8aaee21f1b5399ea375f711e4a30a3997a363ff9881f6eb1137260cc131","task_id":"anchorline-memory-result-ab"},"framework":{"applicable":1,"applicable_ratio":1.0,"evaluable":1,"injection_failed":0,"not_applicable":{"injection_failed":0,"layer_not_targeted":0,"mode_not_applicable":0,"model_not_invoked":0},"oracle_coverage":1.0,"oracle_insufficient":0,"oracle_insufficient_ratio":0.0,"rate_suppressed_reason":"below_min_evaluable","silent_failure_rate":null,"silent_failures":0,"total_runs":1},"model":null,"run_ids":["20261127T145248-20a065b6"]},"framework_rate_difference":null,"model_rate_difference":null,"pair_id":"anchorline-memory-result-surface-v1"}],"run_ids":["20261127T145247-77cdae58","20261127T145248-20a065b6"],"runs":[{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_applied":true,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","observation_status":"not_applicable","run_dir":"runs/_sample/20261127T145247-77cdae58","run_id":"20261127T145247-77cdae58","surface_as":"return_value","target_layers":["framework"],"task_fingerprint":"5742b1fe1bf9f825535f6c468ede7cf407230707380a2c081b10748ee6e9ad56","task_id":"anchorline-memory-result-ab"},{"dependency_lock_hash":"71d51933b1649c54f5f5a999a55d7a06a5bd018138c4b020b3ac538990faff73","experiment_family":"tool_fault","fault_type":"error_response","faultlattice_commit":"a94e2be8a1cd242b3090793e86a6e20db82d1c68","host":"anchorline","host_commit":null,"host_package_version":"0.1.0","inconclusive_threshold":0.5,"injection_applied":true,"injection_point":"tool_result","min_evaluable":2,"mode":"M0","observation_status":"not_applicable","run_dir":"runs/_sample/20261127T145248-20a065b6","run_id":"20261127T145248-20a065b6","surface_as":"raise_exception","target_layers":["framework"],"task_fingerprint":"7209b8aaee21f1b5399ea375f711e4a30a3997a363ff9881f6eb1137260cc131","task_id":"anchorline-memory-result-ab"}],"schema_version":1,"total_runs":2}
```

</details>
