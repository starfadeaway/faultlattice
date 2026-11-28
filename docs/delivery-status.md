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

- 首轮易错点契约真实 M3 重跑：18/18 完成并生成四件套，18 个模型层均为 `explicit_failure`，0 个 Harness 错误；18 个单次公开副本与 3 份本地模型聚合报告均复算通过。
- 独立严格格式与副作用审计：18/18 使用标准 JSON 声明；每个坐标只有一次目标 `write_file`，smolagents 均只有一次 `final_answer`，没有额外重试、探针写入或阻断事件。
- 解释限制：提示词直接规定错误／空／损坏观察声明 `failure`，因此这批结果只证明强提示协议合规，不证明模型独立故障判断；每个坐标一次，不做稳定比例或模型排名。
- 第三轮直接工程修复已落地：YAML 上传白名单、预检默认任务选择、常见进程调用与导入别名 AST 防护、故障 M3 预注册一致性、合规任务文字和文档口径。处理记录见 `reports/external/2026-11-28-third-round-review-triage.md`。
- 最新完整测试：345 passed；第三轮核心修复与公开样例定向回归为 115 项通过。
- Ruff：通过；Pyright：0 errors、0 warnings、0 informations。
- 公开样例专项复算：68 passed。现包含 59 个单次四件套：27 个历史样例、14 个新契约真实 M3 样例和本轮 18 个首轮契约真实 M3 样例；4 个历史公开批次报告也保持复算一致。
- 研发视图 ESLint、TypeScript 与生产构建通过，保留既存大 chunk 提示。验收时 `5173`、`8001`、`7100` 均未监听，因此本轮没有宣称浏览器逐控件实测，也没有为验证重启后再关闭服务。
- 历史新契约 M3 补跑仍保持 14 个完成、11 个 `explicit_failure`、3 个 `inconclusive`、4 个 Harness 错误，未因新结果回改。
- 私有历史派生报告迁移：先备份原 `report.md`，再只重渲染 63 份派生正文；最终 95 份完整四件套全部通过当前模板复算，0 份不一致。每份 `run.json`、`steps.jsonl`、`oracle.jsonl` 迁移前后 SHA-256 完全一致，verdict 未改；备份和哈希清单位于 `.verify/local-report-migration-20261128T232450/`。
- 确定性本地行为门禁：由此前当前代码现场生成独立 current，1 个完整坐标通过；输出写入 `runs/_quality/`，不修改跟踪报告。
- 仓库卫生检查与 `git diff --check`：通过；真实 `.env` 与私有运行目录不由 Git 跟踪。
- 提交 `e7a60328b2d63d858ab23eda58f56a24870e2eb6` 的 GitHub Actions run `46151520301` 已核实为 `completed / success`，Ubuntu 与 Windows 均成功。
- 两批新契约报告、32 个真实 M3 公开样例、调用前协议与工具阻断，以及第三轮工程修复均不包含在上述 `e7a6032` 远端提交中；它们须由后续独立提交和双平台工作流验收，最新提交与 CI 状态以 GitHub 记录为准。
- 公开 CI 所需 M0 源轨迹已进入 `runs/_sample/`，四件套可独立复算；清单仅把本机绝对目录改为相对公开目录。

## 五、已知限制

1. 真实模型实验属于单次或小样本定性案例，未达到预注册 `min_evaluable` 时沉默失败率为 `N/A`，不得解释为稳定性能排名。
2. 首轮契约 18/18 的结论受提示词预期取值约束；空返回与畸形观察任务文字现已明确要求声明 `failure`，与预注册保持一致，`unknown` 仍是 `inconclusive`。独立判断实验必须另建提示条件和预注册，不能沿用本轮标签外推。
3. 本地受控宿主不支持 M3 和 observation 注入；smolagents 当前登记两个 M3 场景，LangGraph 登记四个 M3 场景。历史新契约批次的 4 个 Harness 错误和 3 个证据不足继续保留，本轮 0 错误不回写历史。
4. 历史 MiniMax 三个换行围栏声明继续保持 `inconclusive`。当前解析器已兼容该显式格式，新批次 18/18 使用标准 JSON；额外工具重试和探针文件仍未形成独立 Oracle 维度，阻断逻辑本轮未被真实违规输入触发。
5. AST 已覆盖常见 subprocess／os 直接进程调用、`shutil.rmtree` 和已识别导入别名；动态调用、未知别名和其它创建方式仍可能漏检。该机制只是可信本地草案的静态护栏，不是安全沙箱。
6. 私有 63 份历史派生报告已在用户确认后完成备份和迁移；原始三件产物及 verdict 未改。公开样例与私有报告的通过数量分别陈述，备份清单不参与公开仓库提交。
7. 本地同步工具可使用独立进程执行真实硬超时；smolagents／LangGraph 尚不支持该模式。进程模式不保证清理 worker 的后代进程，也不是不可信代码安全沙箱。
8. 外部 Agent 接入面向可信本地 Python `HostAdapter`，不是任意黑盒程序的自动包装器；登记和预检会执行适配器顶层代码与构造函数。
9. AI 只辅助生成任务、适配器、修改建议和分析文本，不参与确定性实验流程或 Oracle 判定；草案必须经过校验和人工确认。
10. MySQL 是原始四件套之外的可重建索引，LanceDB 相似度不是成功率；外部依赖的实机结果仅覆盖报告列出的环境与小样本。
11. Docker、PyPI 发布和更多宿主／任务覆盖不属于本次已交付能力，不以空配置或占位页面冒充完成。
