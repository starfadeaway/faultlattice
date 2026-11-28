# FaultLattice 交付状态与验收清单

本文记录当前版本的实际交付范围、验证命令和已知限制。状态以真实文件、测试及 CI 结果为依据，不把单次实验外推为普遍可靠性结论。

## 一、交付结论

开发提示词明确列出的阶段 0、阶段 1、阶段 2，以及其后六项功能均已落地：

1. 工程骨架、规范、命名登记与最小 CLI；
2. Pydantic Schema、五类 Oracle、Golden Cases、canonical JSON、原子写入和基础 CI；
3. `run / replay / report / verify` 纵向切片，以及 M0–M2 本地受控实验；
4. FastAPI + React 研发视图与 `run_all.py` 一键启动；
5. smolagents 1.26.0 真实宿主适配；
6. LangGraph 1.2.24 异构宿主适配；
7. M3 真实模型反事实续跑协议与 OpenAI 兼容模型适配；
8. MySQL 可重建索引与 LanceDB 相似故障检索；
9. baseline / current CI 回归质量门禁。

在此之上，当前仓库还包含外部 Agent 接入、任务与适配器草案队列、LLM 修改建议、跨批次分析和 Markdown 下载等已经接线的功能。

“阶段完成”表示代码、测试与指定验收项通过，不表示全部宿主、模型和故障组合均已有充分真实样本，也不表示后续不再扩充平台功能。

## 二、主要交付入口

| 范围 | 实际入口 |
|---|---|
| 安装与能力说明 | `README.md` |
| 执行契约 | `docs/spec-v0.1.md` |
| 命名约束 | `docs/NAMING.md` |
| 实验操作 | `docs/experiment-guide.md` |
| 核心包与 CLI | `src/faultlattice/` |
| 预注册任务与套件 | `tasks/`、`experiments/suites.yaml` |
| 研发与实验控制台 | `console/`、`run_all.py` |
| 外部 Agent 接入 | `external_agents/`、`examples/external_agent/` |
| 公开实验报告 | `reports/README.md` |
| 可复算原始四件套 | `runs/_sample/<run_id>/` |
| 项目模块及验收依赖 | `project.manifest.yaml` |
| 双平台自动化检查 | `.github/workflows/ci.yml` |
| 开源许可证 | `LICENSE`（MIT） |

## 三、实际验证命令

环境与依赖统一使用 uv：

```bash
uv sync --locked --group smolagents --group langgraph --group models --group mysql --group similarity
uv run pytest
uv run ruff check .
uv run pyright
uv run pytest tests/architecture/test_imports.py
uv run python scripts/check_repo_hygiene.py
```

研发视图：

```bash
npm ci --prefix console/web
npm run lint --prefix console/web
npm run build --prefix console/web
uv run python run_all.py
```

公开样例复算：

```bash
uv run faultlattice verify runs/_sample/20261124T124335-94ebab0a
```

独立本地行为门禁与外部公开产物复算：

```bash
uv run python scripts/check_public_regression.py \
  --baseline quality/public-sample.yaml --output runs/_quality/quality-gate.md

# 只验证公开四件套与报告完整性，不声称在 CI 重跑外部生产 Agent。
uv run pytest tests/meta/test_public_samples.py -q
```

## 四、最近一次验收结果

- 第二轮互评修复后的当前工作区完整测试：282 passed。
- Ruff：通过；Pyright：0 errors、0 warnings、0 informations。
- 研发视图 ESLint 与生产构建：通过；保留既存大 chunk 提示。
- 27 个公开单次样例与 4 个公开批次报告均重渲染并独立复算一致；历史任务、轨迹和 Oracle 未回改。
- 确定性本地行为门禁：由当前代码现场生成独立 current，1 个完整坐标通过；输出写入 `runs/_quality/`，不修改跟踪报告。
- 外部 Agent 公开产物：只做四件套与报告完整性复算，不再把同源自比较称为行为回归。
- 仓库卫生检查：通过；真实 `.env` 与私有运行目录不由 Git 跟踪。
- 已通过 GitHub API 核实提交 `170292f02c9a3d09971374daa1ea99e232d0d454` 的 run `46146148387` 为 `completed / success`。当前第二轮修复尚未提交或推送，该记录不替代新工作区的远端双平台验收。
- 公开 CI 所需 M0 源轨迹已进入 `runs/_sample/`，四件套可独立复算；清单仅把本机绝对目录改为相对公开目录。
- 报告列表、本轮正式答复正文接口、后端健康与前端入口均实际访问成功；历史成功不替代新提交验收。

后续提交仍须重新通过同一双平台工作流；历史成功不替代新提交验收。

## 五、已知限制

1. 真实模型实验属于单次或小样本定性案例，未达到预注册 `min_evaluable` 时沉默失败率为 `N/A`，不得解释为稳定性能排名。
2. 本地受控宿主不支持 M3 和 observation 注入；smolagents 当前登记两个 M3 场景，LangGraph 登记四个 M3 场景。
3. 本地同步工具可使用独立进程执行真实硬超时；smolagents／LangGraph 尚不支持该模式。进程模式不保证清理 worker 的后代进程，也不是不可信代码安全沙箱。
4. 外部 Agent 接入面向可信本地 Python `HostAdapter`，不是任意黑盒程序的自动包装器；登记和预检会执行适配器顶层代码与构造函数。
5. AI 只辅助生成任务、适配器、修改建议和分析文本，不参与确定性实验流程或 Oracle 判定；草案必须经过校验和人工确认。
6. MySQL 是原始四件套之外的可重建索引，LanceDB 相似度不是成功率；外部依赖的实机结果仅覆盖报告列出的环境与小样本。
7. Docker、PyPI 发布和更多宿主／任务覆盖不属于本次已交付能力，不以空配置或占位页面冒充完成。
