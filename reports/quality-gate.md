# FaultLattice CI 回归质量门禁

- Baseline：public-local-write-m0
- 结论：通过
- 运行数：baseline 1，current 1
- 成功配对坐标：1
- 违规项：0

本门禁只检查相对回归，不替代 pytest、Ruff、Pyright，也不证明被测 Agent 没有缺陷。
沉默失败率是描述性指标；可判定数低于任务预注册 min_evaluable、没有可判定样本或证据不足
超过阈值时，仅显示对应抑制原因，不形成稳定比例结论。
无故障运行的可判定数保持为 0，另比较逐层判定是否变化；该检查不评价 Oracle 本身是否正确。

## 完整坐标比较

| 任务 | 宿主 | 模式 | 故障族 | 注入点 | 故障类型 | 呈现方式 | 运行数 B/C | 注入失败 B/C | 层 | 可判定 B/C | 无故障判定 B/C | 最低样本 | 比例结论状态 |
|---|---|---|---|---|---|---|---:|---:|---|---:|---|---:|---|
| local_write | local_controlled | M0 | tool_fault | tool_args | invalid_args | raise_exception | 1/1 | 0/0 | framework | 1/1 | N/A / N/A | 3 | below_min_evaluable |


## 违规项

未发现登记的回归条件。该结论只覆盖当前 baseline 与 current 的配对范围。


```json faultlattice-quality-gate
{"baseline_name":"public-local-write-m0","baseline_runs":1,"comparisons":[{"baseline_injection_failures":0,"baseline_no_fault_verdicts":[],"baseline_runs":1,"coordinate":{"experiment_family":"tool_fault","fault_type":"invalid_args","host":"local_controlled","injection_point":"tool_args","mode":"M0","model_id":null,"reasoning_mode":null,"surface_as":"raise_exception","task_id":"local_write"},"current_injection_failures":0,"current_no_fault_verdicts":[],"current_runs":1,"layers":[{"baseline_contract_violations":0,"baseline_evaluable":1,"baseline_silent_failures":0,"current_contract_violations":0,"current_evaluable":1,"current_silent_failures":0,"layer":"framework","min_evaluable":3,"rate_stability":"below_min_evaluable"}]}],"current_runs":1,"matched_coordinates":1,"passed":true,"schema_version":1,"violations":[]}
```
