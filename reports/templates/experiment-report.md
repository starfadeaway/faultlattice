# 实验报告模板

> 使用说明：复制本模板到 `reports/baselines/` 或 `reports/external/` 下填写。
> 所有数字必须来自真实运行，可用 `faultlattice verify runs/_sample/<run_id>` 复算。
> 不允许预填推测数字；没有数据的章节写"未运行"并说明原因。

## 1. 概述

- 实验日期：
- 实验单元 / `pair_id`（如为 A/B 对照）：
- 一句话结论（无结论时写"数据不足，无法下结论"）：

## 2. 被测宿主及版本

| 字段 | 值 |
|---|---|
| 宿主名称 | |
| 宿主包版本 | |
| 宿主 commit（可获得时） | |
| FaultLattice commit | |
| Python 版本 | |
| dependency_lock_hash | |
| 模型 ID（M3） | |
| 采样参数（M3） | |

## 3. 实验任务与故障配置

- 任务定义文件（预注册）：
- 执行模式（M0–M3）：
- `injection_point` / `fault_type` / `surface_as` / `experiment_family`：

## 4. 预注册预期

> 必须在看到结果前从任务定义文件原样摘录。

- `target_layers`：
- `expected_postcondition`：
- `expected_behavior`：
- 故障是否可恢复 / 允许的降级行为：
- `min_evaluable`：
- inconclusive 阈值及超限后的报告规则：

## 5. Oracle 与指标口径

- Oracle `source` / `determinism` / `validation`：
- 沉默失败率口径（分母 = 该层可判定运行数）：
- Oracle 覆盖率口径（分母 = 该层适用集大小）：

## 6. 执行命令

```bash
# 完整可复现命令
```

## 7. 原始样例入口

- `runs/_sample/<run_id>/`（含 `run.json` / `steps.jsonl` / `oracle.jsonl` / `report.md`）
- 复算命令：`faultlattice verify runs/_sample/<run_id>`

## 8. 结果

### 8.1 框架层

| 指标 | 值 |
|---|---|
| 总运行数 | |
| 注入失败数 | |
| 适用集大小（/ 总运行数） | |
| 可判定运行数 | |
| 沉默失败次数 | |
| 沉默失败率 | |
| Oracle 覆盖率 | |
| oracle_evidence_insufficient（占适用集比例，不含 injection_failed） | |
| not_applicable 分原因计数 | |

### 8.2 模型层（未评价时删除本节并注明原因）

同上表结构。

### 8.3 A/B 对照（如适用）

A 组 / B 组分别列出样本数、可判定数、沉默失败率；两组差值仅作描述性对比，不替代任一组的沉默失败率。

## 9. 分层明细

按"宿主 × 执行模式 × experiment_family × injection_point × fault_type × surface_as"完整列出，不合并不同实验条件。

## 10. 限制

- 本报告结论的适用边界；
- 已知的证据不足项；
- 小样本定性结论不得外推为稳定性能结论。

## 11. 异常与后续

- 是否发现异常行为：
- 后续 issue / PR（没有真实发现时不为凑数提交）：
