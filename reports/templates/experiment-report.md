# 实验报告模板

> 用途：复制到 `reports/baselines/` 或 `reports/external/`，填写一次已经完成的实验。
> 本模板故意不预填实验数字。没有运行的项目写“未运行”并说明原因；不得把示例、目标值或历史结果写成本次实测。
> 已填写的真实样例见 `reports/external/2026-11-27-anchorline-lorekeeper-m0-acceptance.md`。

## 1. 结论速览

先用一段中文回答“测了什么、实际发生了什么、能推出什么”。不要把 `completed` 直接翻译成“测试通过”。

| 阅读项 | 本次实际值 | 证据入口 |
|---|---|---|
| Harness 执行状态 | 填写 completed / failed / 未运行 | 套件历史或批次记录 |
| 业务任务是否完成 | 填写是 / 否 / 证据不足 | 后置状态观察，而非最终回答 |
| 框架向调用方报告 | 填写 completed / failed / 未记录 | `run_end.framework_outcome` |
| 故障是否实际生效 | 填写是 / 否 / 无故障基线 | `run.json.injection_applied` |
| 框架层 Oracle | 填写中文结论与原始标识 | `oracle.jsonl` |
| 模型层 Oracle | 填写判定；未评价时写不适用及原因 | `oracle.jsonl` |

- 实验日期（含时区）：
- 实验单元 / `pair_id`（没有 A/B 时明确写“无”）：
- 一句话结论：
- 结论边界：写明本次是单次定性案例还是达到样本阈值的聚合结果。

## 2. 被测对象与冻结环境

| 字段 | 本次实际值 | 填写来源 |
|---|---|---|
| 宿主名称 | | `run.json.task.host` |
| 宿主包版本 | | `run.json.versions.host_package_version` |
| 宿主 commit / 源码快照 | | 没有 commit 时说明快照位置和适配器 SHA-256 |
| FaultLattice commit | | `run.json.versions.faultlattice_commit` |
| Python 版本 | | `run.json.versions.python_version` |
| dependency_lock_hash | | `run.json.versions.dependency_lock_hash` |
| 模型 ID（仅 M3） | | 启动时实际冻结的模型，不填推荐默认值 |
| 思考模式（仅 M3） | | default / enabled / disabled |
| 采样参数（仅 M3） | | 启动时冻结的参数；M0–M2 写不适用 |

若实际依赖与外部项目声明版本不同，单独列出偏差及其影响；不得声称整套外部项目已在原依赖环境下验收。

## 3. 任务目标与故障配置

### 3.1 业务任务

- 任务 ID：
- 任务定义文件（运行前冻结）：
- 用一句人话说明用户要完成什么：
- 实际调用的生产工具或生产循环：
- 执行模式（M0–M3）及该模式能证明什么：

### 3.2 故障坐标

| 字段 | 本次值 | 含义 |
|---|---|---|
| `experiment_family` | | 工具故障或上下文损坏 |
| `injection_point` | | 参数、工具结果或模型观察 |
| `fault_type` | | 超时、空响应、非法参数等 |
| `surface_as` | | 普通返回值、显式异常或不适用 |
| 注入参数 | | 用中文说明实际改了什么，再附必要字段 |

## 4. 运行前预注册的验收契约

> 必须在看到结果前从任务定义原样摘录；运行后不得为迎合结果修改。

- `target_layers`：
- `expected_behavior`（宿主应怎样处理）：
- `expected_postcondition`（实际状态应是什么）：
- 故障是否可恢复：
- 允许的降级行为：
- `min_evaluable`：
- inconclusive 阈值及超限后的报告规则：

## 5. Oracle 与指标口径

- Oracle `source` / `determinism` / `validation`：
- Oracle 如何判断业务成功，所需证据来自哪里：
- 沉默失败率：沉默失败数 ÷ 该层可判定运行数。
- Oracle 覆盖率：可判定运行数 ÷ 该层适用集大小。
- 样本不足时保留原始计数，比例写 N/A；单次运行不宣称稳定失败率。
- `contract_violation`、`explicit_failure`、`silent_failure` 与 Harness 错误分别解释，不混算。

## 6. 执行与复算

```bash
# 填写实际执行命令；不要用“可参考”代替本次真实入口
```

```bash
uv run faultlattice verify runs/<run_id>
```

批次报告另写实际的 `batch-report` / `batch-verify` 命令。若复算未执行，必须写“未复算”及原因。

## 7. 实际过程与状态证据

按真实顺序概述：模型输出是否为预设 → 调用了什么工具 → 注入改变了什么 → 工具实际返回什么 → 宿主如何结束。

| 核对项 | 实际观察 | 证据来源 |
|---|---|---|
| 原始工具参数 | | `steps.jsonl` |
| 注入后的参数或结果 | | `steps.jsonl` |
| 工具真实副作用 | | 独立文件、数据库或宿主状态观察 |
| 最终回答 | | 标明真实模型或预设脚本 |
| 最终框架信号 | | `run_end` |

## 8. 结果

### 8.1 分层判定

| 任务 / 运行 | Harness | 业务任务 | 框架信号 | 框架层 Oracle | 模型层 Oracle |
|---|---|---|---|---|---|
| | | | | | |

### 8.2 指标

| 指标 | 框架层 | 模型层 |
|---|---:|---:|
| 总运行数 | | |
| 注入失败数 | | |
| 适用集大小 | | |
| 可判定运行数 | | |
| 沉默失败次数 | | |
| 沉默失败率 | | |
| Oracle 覆盖率 | | |
| 证据不足次数 | | |
| 不适用原因计数 | | |

### 8.3 A/B 对照（没有时写“无”）

分别列出 A、B 的样本数、可判定数与沉默失败率。两组差值只作描述，不替代各组自身口径。

## 9. 原始产物入口

- 单次运行：`runs/<run_id>/`。
- 四件套：`run.json`、`steps.jsonl`、`oracle.jsonl`、`report.md`。
- 公开脱敏副本（只有真实存在时才填写）：`runs/_sample/<run_id>/`。
- 原始 JSON 放入 `<details>` 折叠区，并标注“机器审计用”；正文先给人读结论和证据表。

## 10. 异常、修改建议与后续

- 实际发现的异常及证据：
- AI 修改建议是否生成；若失败，记录错误，不把空建议写成已生成：
- 建议是否经过人工复核；建议不得自动修改源码、任务预期或 Oracle：
- 后续实验、issue / PR（没有真实发现时不凑数）：

## 11. 限制

逐项写明样本量、执行模式、宿主版本、依赖偏差、未覆盖故障、Oracle 验证状态和证据缺口。单次 M0 不能证明真实模型行为，单次 M3 也不能证明稳定模型表现。
