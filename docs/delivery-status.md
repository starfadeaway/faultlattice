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

- 第五轮核心修复：模型提供方必须显式声明 `state_claim_protocol`，任务与提供方协议不一致时在真实模型调用前拒绝；运行索引排除 `_quality`、空目录和 `harness_failed` 审计目录，同时继续拒绝损坏的完整运行。处理记录见 `reports/external/2026-11-29-fifth-round-review-triage.md`。
- 控制台与报告已补齐协议维度：实验页、套件报告、分析页和 LLM 聚合证据按协议区分；独立判断中的 `completed` 明示为“符合预注册”，unknown 情形不代表业务成功。新增 `m3-independent-judgment` 套件和 6 个公开预注册任务，仅验证可加载，未自动调用模型。
- 独立判断试点保持原始判定：18 次中 15 个完整复算、3 个 Harness 失败；9 个 failure、6 个 unknown，1 个预注册不匹配。每坐标一次，不作模型排名、稳定比例或因果归因。5 个 unknown 完整运行的派生报告只修复展示措辞，原始三件产物与 verdict 未改。
- 第四轮核心修复：内置宿主异常时保留 `run.json + steps.jsonl`，清单标记 `execution_status=harness_failed` 并记录异常和轨迹哈希；控制台可通过 `run_id` 找回失败目录。失败审计产物不生成 Oracle、不冒充完整四件套、不计入有效样本。处理记录见 `reports/external/2026-11-29-fourth-round-review-triage.md`。
- 可控 LangGraph 回归证明：续跑违规业务工具调用在执行前阻断后，`blocked_tool_calls`、工具边界、目标写入、故障注入、失败 `run_end` 和异常 `run_id` 均已落盘；探针文件不存在。该测试使用伪模型，不是新增真实模型实验。
- 首轮易错点契约真实 M3 重跑仍是：18/18 完成并生成四件套，18 个模型层均为 `explicit_failure`，0 个 Harness 错误；18 个单次公开副本复算通过，3 份模型聚合报告为本地非公开审计产物。
- 三个独立判断 Harness 失败已另建单次后续实验：DeepSeek / smolagents 与 MiniMax / LangGraph 错误观察坐标完成并复算，MiniMax / LangGraph 空返回仍删除目标末尾换行，在写入前严格拒绝。smolagents 现在对非原生 `final_answer` 立即记录明确协议错误，不进入异常记忆；适配器不自动补参或把 DSML 文本伪装成工具调用。详见 `reports/external/2026-11-29-harness-failure-followup.md`。
- 最新完整测试：374 passed（包含新增 2 个公开样例复算）。
- Ruff：通过；Pyright：0 errors、0 warnings、0 informations。
- 公开样例现有 76 个单次四件套和 4 个历史公开批次；独立判断试点新增 15 个完整运行，后续实验新增 2 个，未改写既有真实模型结果。公开行为回归门禁通过。
- 研发视图 ESLint、TypeScript 与生产构建通过，保留既存大 chunk 提示。本轮未重启服务或进行逐控件浏览器测试，不外推为完整交互覆盖。
- 历史新契约 M3 补跑仍保持 14 个完成、11 个 `explicit_failure`、3 个 `inconclusive`、4 个 Harness 错误，未因新结果回改；当时已经丢失的错误轨迹不由新代码伪造补齐。
- 私有历史派生报告迁移基线仍为 95/95 完整四件套复算通过；63 份只重渲染派生正文，原始三件产物与 verdict 未改。
- 确定性本地行为门禁使用当前代码现场生成 independent current；输出写入 `runs/_quality/`，不修改跟踪报告。
- 仓库卫生检查与 `git diff --check`：通过；真实 `.env`、`reviews/` 与私有运行目录不由 Git 跟踪。
- 被审查提交 `cd531a7fba0e9ce4dd6a440153924e29cf7d5715` 的 GitHub Actions run `46161500683` 已核实为 `completed / success`，Ubuntu 与 Windows 均成功。
- 第四轮修复提交 `b5dd7dd9398d61071625b4b0746a2b735c05d992` 已公开推送；对应 GitHub Actions run `46165131495` 为 `completed / success`，Ubuntu 与 Windows 均成功，与本地 348 项测试及前端检查结果一致。
- 第五轮修复提交 `87c8a1b454a136e5bd075a975ac01036ccae374b` 已公开推送；对应 GitHub Actions run `46170613656` 已完成，Ubuntu job `141057962278` 与 Windows job `141057962535` 均为 `completed / success`，与本地 370 项测试及前端检查结果一致。
- 公开 CI 所需源轨迹已进入 `runs/_sample/`，四件套可独立复算；清单仅把本机绝对目录改为相对公开目录。

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
