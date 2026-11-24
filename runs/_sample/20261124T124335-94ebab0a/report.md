# FaultLattice 运行报告 20261124T124335-94ebab0a

- 任务：local_write（宿主 local_controlled，模式 M0）
- 故障：tool_args / invalid_args / raise_exception（tool_fault）
- injection_applied：True；observation_status：not_applicable
- 预注册 target_layers：['framework']

## 框架层指标

| 指标 | 值 |
|---|---|
| 总运行数 | 1 |
| 注入失败数 | 0 |
| 适用集大小（/ 总运行数） | 1（1/1） |
| 可判定运行数 | 1 |
| 沉默失败次数 | 0 |
| 沉默失败率 | 0.00% |
| Oracle 覆盖率 | 100.00% |
| oracle_evidence_insufficient | 0（占适用集 0/1） |
| 框架层 verdict | explicit_failure |

## 模型层指标

本次运行未评价模型层（target_layers 未包含 model）。

## 分层明细

本切片每次报告对应单个运行；分层坐标（宿主 × 模式 × 族 × 注入点 × 故障类型 × surface_as）：
`local_controlled × M0 × tool_fault`
`tool_args × invalid_args × raise_exception`。

```json faultlattice-metrics
{"framework":{"applicable":1,"applicable_ratio":"1/1","evaluable":1,"injection_failed":0,"not_applicable_reason":null,"oracle_coverage":1.0,"oracle_coverage_display":"100.00%","oracle_insufficient":0,"oracle_insufficient_ratio":"0/1","silent_failure_rate":0.0,"silent_failure_rate_display":"0.00%","silent_failures":0,"total_runs":1,"verdict":"explicit_failure"},"model":null,"run_id":"20261124T124335-94ebab0a","task_id":"local_write"}
```
