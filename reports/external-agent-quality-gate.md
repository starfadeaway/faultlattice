# FaultLattice CI 回归质量门禁

- Baseline：public-external-agent-m0
- 结论：通过
- 运行数：baseline 6，current 6
- 成功配对坐标：6
- 违规项：0

本门禁只检查相对回归，不替代 pytest、Ruff、Pyright，也不证明被测 Agent 没有缺陷。
沉默失败率是描述性指标；可判定数低于任务预注册 min_evaluable、没有可判定样本或证据不足
超过阈值时，仅显示对应抑制原因，不形成稳定比例结论。
无故障运行的可判定数保持为 0，另比较逐层判定是否变化；该检查不评价 Oracle 本身是否正确。

## 完整坐标比较

| 任务 | 宿主 | 模式 | 故障族 | 注入点 | 故障类型 | 呈现方式 | 运行数 B/C | 注入失败 B/C | 层 | 可判定 B/C | 无故障判定 B/C | 最低样本 | 比例结论状态 |
|---|---|---|---|---|---|---|---:|---:|---|---:|---|---:|---|
| anchorline-memory-result-ab | anchorline | M0 | tool_fault | tool_result | error_response | raise_exception | 1/1 | 0/0 | framework | 1/1 | N/A / N/A | 2 | below_min_evaluable |
| anchorline-memory-result-ab | anchorline | M0 | tool_fault | tool_result | error_response | return_value | 1/1 | 0/0 | framework | 1/1 | N/A / N/A | 2 | below_min_evaluable |
| anchorline-memory-result-error | anchorline | M0 | tool_fault | tool_result | error_response | return_value | 1/1 | 0/0 | framework | 1/1 | N/A / N/A | 1 | eligible_descriptive_rate |
| lorekeeper-calculator-invalid-args | lorekeeper | M0 | tool_fault | tool_args | invalid_args | return_value | 1/1 | 0/0 | framework | 1/1 | N/A / N/A | 1 | eligible_descriptive_rate |
| anchorline-memory-result-normal | anchorline | M0 | N/A | N/A | N/A | N/A | 1/1 | 0/0 | framework | 0/0 | framework=completed / framework=completed | 1 | no_evaluable_runs |
| lorekeeper-calculator-normal | lorekeeper | M0 | N/A | N/A | N/A | N/A | 1/1 | 0/0 | framework | 0/0 | framework=completed / framework=completed | 1 | no_evaluable_runs |


## 违规项

未发现登记的回归条件。该结论只覆盖当前 baseline 与 current 的配对范围。


```json faultlattice-quality-gate
{"baseline_name":"public-external-agent-m0","baseline_runs":6,"comparisons":[{"baseline_injection_failures":0,"baseline_no_fault_verdicts":[],"baseline_runs":1,"coordinate":{"experiment_family":"tool_fault","fault_type":"error_response","host":"anchorline","injection_point":"tool_result","mode":"M0","surface_as":"raise_exception","task_id":"anchorline-memory-result-ab"},"current_injection_failures":0,"current_no_fault_verdicts":[],"current_runs":1,"layers":[{"baseline_contract_violations":1,"baseline_evaluable":1,"baseline_silent_failures":0,"current_contract_violations":1,"current_evaluable":1,"current_silent_failures":0,"layer":"framework","min_evaluable":2,"rate_stability":"below_min_evaluable"}]},{"baseline_injection_failures":0,"baseline_no_fault_verdicts":[],"baseline_runs":1,"coordinate":{"experiment_family":"tool_fault","fault_type":"error_response","host":"anchorline","injection_point":"tool_result","mode":"M0","surface_as":"return_value","task_id":"anchorline-memory-result-ab"},"current_injection_failures":0,"current_no_fault_verdicts":[],"current_runs":1,"layers":[{"baseline_contract_violations":1,"baseline_evaluable":1,"baseline_silent_failures":0,"current_contract_violations":1,"current_evaluable":1,"current_silent_failures":0,"layer":"framework","min_evaluable":2,"rate_stability":"below_min_evaluable"}]},{"baseline_injection_failures":0,"baseline_no_fault_verdicts":[],"baseline_runs":1,"coordinate":{"experiment_family":"tool_fault","fault_type":"error_response","host":"anchorline","injection_point":"tool_result","mode":"M0","surface_as":"return_value","task_id":"anchorline-memory-result-error"},"current_injection_failures":0,"current_no_fault_verdicts":[],"current_runs":1,"layers":[{"baseline_contract_violations":1,"baseline_evaluable":1,"baseline_silent_failures":0,"current_contract_violations":1,"current_evaluable":1,"current_silent_failures":0,"layer":"framework","min_evaluable":1,"rate_stability":"eligible_descriptive_rate"}]},{"baseline_injection_failures":0,"baseline_no_fault_verdicts":[],"baseline_runs":1,"coordinate":{"experiment_family":"tool_fault","fault_type":"invalid_args","host":"lorekeeper","injection_point":"tool_args","mode":"M0","surface_as":"return_value","task_id":"lorekeeper-calculator-invalid-args"},"current_injection_failures":0,"current_no_fault_verdicts":[],"current_runs":1,"layers":[{"baseline_contract_violations":0,"baseline_evaluable":1,"baseline_silent_failures":0,"current_contract_violations":0,"current_evaluable":1,"current_silent_failures":0,"layer":"framework","min_evaluable":1,"rate_stability":"eligible_descriptive_rate"}]},{"baseline_injection_failures":0,"baseline_no_fault_verdicts":["framework=completed"],"baseline_runs":1,"coordinate":{"experiment_family":null,"fault_type":null,"host":"anchorline","injection_point":null,"mode":"M0","surface_as":null,"task_id":"anchorline-memory-result-normal"},"current_injection_failures":0,"current_no_fault_verdicts":["framework=completed"],"current_runs":1,"layers":[{"baseline_contract_violations":0,"baseline_evaluable":0,"baseline_silent_failures":0,"current_contract_violations":0,"current_evaluable":0,"current_silent_failures":0,"layer":"framework","min_evaluable":1,"rate_stability":"no_evaluable_runs"}]},{"baseline_injection_failures":0,"baseline_no_fault_verdicts":["framework=completed"],"baseline_runs":1,"coordinate":{"experiment_family":null,"fault_type":null,"host":"lorekeeper","injection_point":null,"mode":"M0","surface_as":null,"task_id":"lorekeeper-calculator-normal"},"current_injection_failures":0,"current_no_fault_verdicts":["framework=completed"],"current_runs":1,"layers":[{"baseline_contract_violations":0,"baseline_evaluable":0,"baseline_silent_failures":0,"current_contract_violations":0,"current_evaluable":0,"current_silent_failures":0,"layer":"framework","min_evaluable":1,"rate_stability":"no_evaluable_runs"}]}],"current_runs":6,"matched_coordinates":6,"passed":true,"schema_version":1,"violations":[]}
```
