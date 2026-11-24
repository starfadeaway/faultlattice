# FaultLattice

> Agent Reliability Harness & Evaluation Platform

FaultLattice 是一个 Agent 可靠性注入实验与评测工具：对宿主 Agent 框架执行受控故障注入、轨迹记录与重放，并用预注册的 Oracle 判定框架层与模型层行为，产出可复算的实验报告。

## 快速安装与运行

要求：Python >= 3.13，uv。

```bash
uv sync
uv run faultlattice --help
uv run pytest
```

依赖与环境统一由 uv 管理（`pyproject.toml` + `uv.lock`），不混用 venv+pip 工作流。

## 当前已实现能力

- 核心 schema（Pydantic v2）：FaultSpec 合法组合校验、任务预注册、轨迹事件、Oracle 判定记录、run.json 运行清单；
- 故障模型：13 种合法组合（spec 第 3 节），非法组合直接报配置错误；
- Oracle 判定器：框架层 / 模型层判定树，配 10 个 golden cases 与元测试；
- canonical JSON（排序键 / UTF-8 / LF / 禁 NaN）、SHA-256、原子写入，双平台测试；
- CLI 纵向切片：`run` / `replay`（M1 纯轨迹、M2 故障注入）/ `report` / `verify`；
- 本地受控测试宿主（确定性工具调用程序，支持 tool_args / tool_result 注入）；
- AST 依赖方向检查、仓库卫生检查、GitHub Actions CI（ubuntu + windows）。

## 当前限制

- 仅 M0–M2；M3 反事实续跑只有协议预留（`ModelProvider` / `CounterfactualRunner` 未实现）；
- 本地宿主不支持 observation 注入（无独立 observation 通道，预检显式报错）；
- 报告粒度为单次运行；跨运行批次聚合、A/B 配对硬校验、min_evaluable 批次门禁未实现；
- 评测平台（FastAPI + React 研发视图）、smolagents adapter、MySQL / LanceDB 均未开始；
- 同步工具超时仅为确定性模拟 `TimeoutError`，不代表真实硬终止（spec 第 3 节）。

## 文档入口

- 规范：[docs/spec-v0.1.md](docs/spec-v0.1.md)
- 命名登记：[docs/NAMING.md](docs/NAMING.md)
- 公开报告索引：[reports/README.md](reports/README.md)

## 公开样例

[runs/_sample/20261124T124335-94ebab0a](runs/_sample/20261124T124335-94ebab0a) 是一次完整的 M0 运行四件套（`tool_args / invalid_args / raise_exception`，框架层判定 `explicit_failure`）。可直接复算：

```bash
faultlattice verify runs/_sample/20261124T124335-94ebab0a
```
