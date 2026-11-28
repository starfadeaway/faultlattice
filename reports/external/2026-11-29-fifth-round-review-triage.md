# 第五轮模型审查事实核对与修复记录

- 日期：2026-11-29。
- 范围：核对本地两份 DeepSeek / MiniMax 审查附件，并在当前工作区复现其代码级发现。
- 基线说明：两份附件观察的是不同时间的快照，其中若干测试数、CI 状态和“尚未真实运行 independent 协议”的描述已经过时；本记录只处理当前代码仍能复现的问题。
- 最终门禁：370 项 pytest 通过；Ruff、Pyright、仓库卫生、公开行为回归、前端 ESLint、TypeScript 与生产构建、`git diff --check` 全部通过。

## 1. 已修复：模型提供方协议静默回退

**审查发现成立。** 两个 M3 宿主曾使用 `getattr(..., "directive_failure_v1")`，自定义提供方缺少 `state_claim_protocol` 时会收到旧强指令提示，而 Oracle 仍可能按任务中的独立判断协议评价。

处理结果：

1. `ModelProvider` Protocol 新增必需的 `state_claim_protocol` 字段。
2. LangGraph 与 smolagents 直接读取提供方协议，移除默认回退。
3. `CounterfactualRunner` 在真实模型调用前比较任务与提供方协议；缺字段或不一致时抛出 `ConfigurationError`，不执行模型、工具或故障注入。
4. 新增自定义提供方独立提示测试、缺失协议拒绝测试，并同步 NAMING 与规格文档。

这项修复防止今后发生提示口径与 Oracle 口径分裂；已完成的独立判断试点使用 `OpenAICompatibleModel`，其协议字段来自冻结任务，不重跑、不改写实验结果。

## 2. 已修复：运行索引被辅助目录和失败审计阻断

**审查发现成立。** `collect_run_records` 原只排除 `_sample`、`suites`、`_index`，会把 `_quality`、空目录和只有 `run.json + steps.jsonl` 的 Harness 失败目录当成完整四件套。

处理结果：

- 排除 `_quality`，跳过无 `run.json` 的非运行目录和明确标记 `execution_status=harness_failed` 的失败审计目录。
- 对声明为完整运行但缺少四件套文件的目录继续抛出 `ArtifactError`，不以“跳过”掩盖产物损坏。
- 新增辅助目录、失败审计和完整运行损坏三类回归测试。
- 当前实际 `runs/` 已成功提取 110 个完整运行记录。

本轮没有连接 MySQL 或 LanceDB 服务，因此这里只证明索引收集链路恢复，不宣称外部数据库与向量服务已重新验收。

## 3. 已补齐：控制台协议维度与独立判断入口

**审查发现成立。** 控制台此前不展示协议，分析聚合键只有任务、宿主和模式，独立判断中的 `completed` 容易被误读为业务正常。

处理结果：

1. 套件状态逐任务保存 `state_claim_protocol`；旧历史可从模型 Oracle 证据恢复，再按模式使用兼容默认值。
2. 实验页显示预注册协议、实际任务协议及“信息不足不等于业务成功”提示。
3. 套件 Markdown 增加协议汇总和逐任务协议列。
4. 分析页与 LLM 聚合证据按协议拆分任务组；`completed` 改标为“符合预注册”，独立 unknown 情形单独提示。
5. 新增 `m3-independent-judgment` 控制台套件，含 6 个公开预注册任务；明确错误预注册 `failure`，空返回与畸形观察预注册 `unknown`。只验证任务可加载，没有自动发起付费模型调用。

## 4. 已修复：单次报告措辞与派生产物复算

独立判断协议下，预注册与实际声明均为 `unknown` 时，单次报告现将 `completed` 直接写为“符合信息不足预注册（不代表业务成功）”，不再要求读者回到其他章节寻找限制说明。

因此重渲染了 5 个符合该情形的公开及对应私有 `report.md`。逐文件哈希证明 `run.json`、`steps.jsonl`、`oracle.jsonl` 完全未变；声明、预期、verdict 和运行 ID 均未修改。前后哈希保存在本地 `.verify/independent_judgment_pilot/post_review_rerender.json`，试点报告已增加展示修复说明。

## 5. 已修复：本地评审附件隐私

- `.gitignore` 和卫生脚本必需规则均加入 `reviews/`。
- 卫生脚本同时检查 `.env` 与 `reviews/` 是否已被 Git 跟踪。
- 当前 `git check-ignore reviews` 生效，待提交列表不再显示本地评审附件。

《项目进度与互评清单》及原始审查附件继续只保留本地，不进入公开报告或提交。

## 6. 保留为后续工作，不假报完成

1. **恢复类 `success` 证据契约仍未实现。** 当前对错误、空、损坏、超时和截断故障拒绝预注册 `success` 是有意防误判；不能用一个无校验开关宣称支持恢复实验。
2. **样本量、重复测量与消融仍不足。** 独立判断试点每坐标一次，不作模型排名、稳定比例或因果归因。
3. **三个 Harness 失败仍是适配器问题。** 不在原冻结坐标上补跑或改写结果；修复后应另建实验。
4. **外部服务与浏览器行为未重新验收。** 本轮执行了前端静态检查和生产构建，但没有重启服务或逐控件浏览器测试，也没有重跑 MySQL、embedding、LanceDB。
5. **本轮 CI 已独立验收。** 修复提交 `87c8a1b454a136e5bd075a975ac01036ccae374b` 已推送到 `main`；GitHub Actions run `46170613656` 已完成，Ubuntu job `141057962278` 与 Windows job `141057962535` 均为 `completed / success`。旧提交的绿色 CI 不再作为本轮结论依据。
