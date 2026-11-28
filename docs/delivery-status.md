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

- 第四轮核心修复：内置宿主异常时保留 `run.json + steps.jsonl`，清单标记 `execution_status=harness_failed` 并记录异常和轨迹哈希；控制台可通过 `run_id` 找回失败目录。失败审计产物不生成 Oracle、不冒充完整四件套、不计入有效样本。处理记录见 `reports/external/2026-11-29-fourth-round-review-triage.md`。
- 可控 LangGraph 回归证明：续跑违规业务工具调用在执行前阻断后，`blocked_tool_calls`、工具边界、目标写入、故障注入、失败 `run_end` 和异常 `run_id` 均已落盘；探针文件不存在。该测试使用伪模型，不是新增真实模型实验。
- 第四轮配套修复：`truncated` 故障不得预注册成功声明；新运行用 `state_claim_error` 区分空回答与未找到声明；历史 M3 报告增加 Post-fix note，并明确第二批零额外写入受续跑工具边界结构性约束。
- 首轮易错点契约真实 M3 重跑仍是：18/18 完成并生成四件套，18 个模型层均为 `explicit_failure`，0 个 Harness 错误；18 个单次公开副本复算通过，3 份模型聚合报告为本地非公开审计产物。
- 解释限制：提示词直接规定错误／空／损坏观察声明 `failure`，续跑又移除了业务工具，因此这批结果只证明强提示与工具约束下的协议合规，不证明模型独立故障判断或自行学会不重试；每个坐标一次，不做稳定比例或模型排名。
- 第三轮直接工程修复已落地：YAML 上传白名单、预检默认任务选择、常见进程调用与导入别名 AST 防护、故障 M3 预注册一致性、合规任务文字和文档口径。处理记录见 `reports/external/2026-11-28-third-round-review-triage.md`。
- 最新完整测试：348 passed；第四轮失败路径、M3 Schema、双宿主适配器与控制台定向回归为 43 项通过。
- Ruff：通过；Pyright：0 errors、0 warnings、0 informations。
- 公开样例基线仍为 59 个单次四件套和 4 个历史公开批次；本轮没有新增、改写或回填真实模型公开样例。专项复算结果以本轮最终命令输出为准。
- 研发视图 ESLint、TypeScript 与生产构建通过，保留既存大 chunk 提示。此前已在内置浏览器完成 YAML 上传和预检默认任务选择两项真实交互验收；本轮未把它外推为逐控件完整覆盖。
- 历史新契约 M3 补跑仍保持 14 个完成、11 个 `explicit_failure`、3 个 `inconclusive`、4 个 Harness 错误，未因新结果回改；当时已经丢失的错误轨迹不由新代码伪造补齐。
- 私有历史派生报告迁移基线仍为 95/95 完整四件套复算通过；63 份只重渲染派生正文，原始三件产物与 verdict 未改。
- 确定性本地行为门禁使用当前代码现场生成 independent current；输出写入 `runs/_quality/`，不修改跟踪报告。
- 仓库卫生检查与 `git diff --check`：通过；真实 `.env` 与私有运行目录不由 Git 跟踪。
- 被审查提交 `cd531a7fba0e9ce4dd6a440153924e29cf7d5715` 的 GitHub Actions run `46161500683` 已核实为 `completed / success`，Ubuntu 与 Windows 均成功。
- 第四轮修复提交 `b5dd7dd9398d61071625b4b0746a2b735c05d992` 已公开推送；对应 GitHub Actions run `46165131495` 为 `completed / success`，Ubuntu 与 Windows 均成功，与本地 348 项测试及前端检查结果一致。
- 公开 CI 所需 M0 源轨迹已进入 `runs/_sample/`，四件套可独立复算；清单仅把本机绝对目录改为相对公开目录。

## 五、已知限制

1. 真实模型实验属于单次或小样本定性案例，未达到预注册 `min_evaluable` 时沉默失败率为 `N/A`，不得解释为稳定性能排名。
2. 首轮契约 18/18 的结论受提示词预期取值约束；空返回与畸形观察任务文字现已明确要求声明 `failure`，与预注册保持一致，`unknown` 仍是 `inconclusive`。独立判断实验必须另建提示条件和预注册，不能沿用本轮标签外推。
3. 本地受控宿主不支持 M3 和 observation 注入；smolagents 当前登记两个 M3 场景，LangGraph 登记四个 M3 场景。历史新契约批次的 4 个 Harness 错误和 3 个证据不足继续保留，本轮 0 错误不回写历史。
4. 历史 MiniMax 三个换行围栏声明继续保持 `inconclusive`。当前解析器已兼容该显式格式，新批次 18/18 使用标准 JSON；额外工具重试和探针文件仍未形成独立 Oracle 维度。阻断及失败落盘已由可控伪模型回归验证，但首轮真实模型批次没有触发违规阻断。
5. AST 已覆盖常见 subprocess／os 直接进程调用、`shutil.rmtree` 和已识别导入别名；动态调用、未知别名和其它创建方式仍可能漏检。该机制只是可信本地草案的静态护栏，不是安全沙箱。
6. 私有 63 份历史派生报告已在用户确认后完成备份和迁移；原始三件产物及 verdict 未改。公开样例与私有报告的通过数量分别陈述，备份清单不参与公开仓库提交。
7. 本地同步工具可使用独立进程执行真实硬超时；smolagents／LangGraph 尚不支持该模式。进程模式不保证清理 worker 的后代进程，也不是不可信代码安全沙箱。
8. 外部 Agent 接入面向可信本地 Python `HostAdapter`，不是任意黑盒程序的自动包装器；登记和预检会执行适配器顶层代码与构造函数。
9. AI 只辅助生成任务、适配器、修改建议和分析文本，不参与确定性实验流程或 Oracle 判定；草案必须经过校验和人工确认。
10. MySQL 是原始四件套之外的可重建索引，LanceDB 相似度不是成功率；外部依赖的实机结果仅覆盖报告列出的环境与小样本。
11. Docker、PyPI 发布和更多宿主／任务覆盖不属于本次已交付能力，不以空配置或占位页面冒充完成。
12. `harness_failed` 目录只保留失败清单、已暴露事件和真实沙箱，不是完整四件套。自定义外部适配器还需把本次事件列表暴露为 `last_events` 才能在异常时保留详细内部轨迹；恢复类实验则需要另建显式恢复证据契约，当前没有实现。
