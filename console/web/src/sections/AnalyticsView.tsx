import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertOutlined,
  ArrowRightOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  DiffOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
} from "@ant-design/icons"
import { Alert, Button, Empty, Input, Segmented, Select, Spin, Tag } from "antd"
import ReactMarkdown from "react-markdown"
import { useNavigate } from "react-router"
import remarkGfm from "remark-gfm"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts"
import { api } from "../api"
import { MarkdownDownloadButton } from "../components/MarkdownDownloadButton"
import { ParameterDiffView } from "./ParameterDiffView"
import type { AnalysisResult, ModelOption, SuiteRun } from "../types"
import { downloadMarkdown } from "../utils/downloadMarkdown"
import { formatDateTime } from "../utils/dateTime"

const verdictLabels: Record<string, string> = {
  completed: "符合预注册",
  explicit_failure: "显式失败",
  silent_failure: "沉默失败",
  contract_violation: "契约违反",
  inconclusive: "证据不足",
  not_applicable: "本层不适用",
}

const verdictOrder = ["completed", "explicit_failure", "silent_failure", "contract_violation", "inconclusive", "not_applicable"]
const verdictColors: Record<string, string> = {
  completed: "#4ade80",
  explicit_failure: "#fbbf24",
  silent_failure: "#fb7185",
  contract_violation: "#f97316",
  inconclusive: "#94a3b8",
  not_applicable: "#64748b",
}
const statusLabels = { running: "运行中", completed: "执行完成", failed: "Harness 错误" }
const nonEvaluable = ["inconclusive", "not_applicable", "unknown"]

interface TaskAggregate {
  taskId: string
  host: string
  mode: string
  protocol: string
  total: number
  completed: number
  failed: number
  verdicts: Record<string, number>
}

interface AnalysisInsight {
  tone: "risk" | "warning" | "good" | "info"
  title: string
  detail: string
}

interface ScopedAnalysis {
  result: AnalysisResult
  scopeKey: string
  scopeLabel: string
}

interface AnalyticsViewProps {
  defaultAdvisorOptionId: string
  onAdvisorOptionChange: (optionId: string) => void
  motionEnabled: boolean
}

function verdictOf(judgement: Record<string, unknown>): string {
  return typeof judgement.verdict === "string" ? judgement.verdict : "unknown"
}

function layerOf(judgement: Record<string, unknown>): string {
  return judgement.layer === "model" ? "model" : "framework"
}

function evidenceOf(judgement: Record<string, unknown>): Record<string, unknown> {
  return judgement.evidence && typeof judgement.evidence === "object" && !Array.isArray(judgement.evidence)
    ? judgement.evidence as Record<string, unknown>
    : {}
}

function protocolOfTask(task: SuiteRun["tasks"][number]): string {
  if (task.state_claim_protocol) return task.state_claim_protocol
  const recorded = task.judgements.map((judgement) => evidenceOf(judgement).state_claim_protocol)
    .find((value): value is string => typeof value === "string" && Boolean(value))
  return recorded || (task.mode === "M3" ? "directive_failure_v1" : "not_applicable")
}

function protocolLabel(protocol: string): string {
  return {
    directive_failure_v1: "强指令声明",
    independent_judgment_v1: "独立判断",
    not_applicable: "不适用",
  }[protocol] || protocol
}

function percent(value: number, total: number): string {
  return total ? `${(value / total * 100).toFixed(1)}%` : "N/A"
}

function percentNumber(value: number, total: number): number {
  return total ? Number((value / total * 100).toFixed(1)) : 0
}

function markdownCell(value: string): string {
  return value.replaceAll("|", "\\|").replaceAll("\n", " ")
}

function shortBatchTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })
}

function AnalysisTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const first = payload[0]?.payload as { fullName?: string; date?: string; name?: string } | undefined
  return (
    <div className="analysis-chart-tooltip">
      <strong>{first?.fullName || first?.name || label || "当前数据"}</strong>
      {first?.date && <small>{first.date}</small>}
      {payload.map((item) => (
        <div key={String(item.dataKey || item.name)}>
          <span className="analysis-tooltip-dot" style={{ background: item.color || item.payload?.fill }} />
          <span>{item.name}</span>
          <b>{typeof item.value === "number" ? item.value.toLocaleString("zh-CN") : item.value}{item.unit || ""}</b>
        </div>
      ))}
    </div>
  )
}

function llmDocument(analysis: ScopedAnalysis): string {
  return [
    "# FaultLattice 大模型辅助分析",
    "",
    `- 分析模型：${analysis.result.model_id}`,
    `- 生成时间：${formatDateTime(analysis.result.generated_at)}`,
    `- 证据范围：${analysis.scopeLabel}`,
    "",
    "> 本结果只解释聚合实验证据，不代表模型读过完整轨迹或源码；不自动修改代码、任务或 Oracle。",
    "",
    analysis.result.content,
    "",
  ].join("\n")
}

export function AnalyticsView(props: AnalyticsViewProps) {
  const [workspace, setWorkspace] = useState<"verdicts" | "parameters">("verdicts")
  const parameters = workspace === "parameters"
  return (
    <div className="view-stack analytics-view">
      <section className="analysis-intro">
        <div>
          <span className="section-kicker">{parameters ? "PARAMETER FIDELITY" : "EVIDENCE ANALYSIS"}</span>
          <h2>{parameters ? "工具参数差异诊断" : "跨批次实验分析"}</h2>
          <p>{parameters
            ? "对照目标与实际工具参数，定位真实换行、字面转义和额外引号；只读展示公开诊断，不执行工具或修改 Oracle。"
            : "用真实历史生成动态图表和可复算结论；也可以让所选模型解释聚合结果。所有分析都不重新运行实验、不修改 Oracle。"}</p>
        </div>
        {parameters ? <DiffOutlined aria-hidden="true" /> : <BarChartOutlined aria-hidden="true" />}
      </section>
      <Segmented
        className="analysis-workspace-switch"
        value={workspace}
        onChange={(value) => setWorkspace(value as "verdicts" | "parameters")}
        aria-label="选择分析工作区"
        options={[
          { value: "verdicts", label: "实验判定" },
          { value: "parameters", label: "参数差异" },
        ]}
      />
      {parameters ? <ParameterDiffView motionEnabled={props.motionEnabled} /> : <VerdictAnalyticsView {...props} />}
    </div>
  )
}

function VerdictAnalyticsView({ defaultAdvisorOptionId, onAdvisorOptionChange, motionEnabled }: AnalyticsViewProps) {
  const [history, setHistory] = useState<SuiteRun[]>([])
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([])
  const [advisorOptionId, setAdvisorOptionId] = useState(defaultAdvisorOptionId)
  const [query, setQuery] = useState("")
  const [target, setTarget] = useState("all")
  const [layer, setLayer] = useState("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [modelError, setModelError] = useState("")
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState("")
  const [llmAnalysis, setLlmAnalysis] = useState<ScopedAnalysis | null>(null)
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    setModelError("")
    try {
      const [historyData, modelData] = await Promise.all([
        api.experimentHistory(),
        api.experimentModels().catch((reason: unknown) => {
          setModelError(reason instanceof Error ? reason.message : "模型目录读取失败")
          return []
        }),
      ])
      setHistory(historyData)
      setModelOptions(modelData)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "实验历史读取失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!modelOptions.length) {
      if (advisorOptionId) setAdvisorOptionId("")
      return
    }
    const next = modelOptions.some((option) => option.id === advisorOptionId)
      ? advisorOptionId
      : modelOptions.some((option) => option.id === defaultAdvisorOptionId)
        ? defaultAdvisorOptionId
        : modelOptions[0].id
    if (next !== advisorOptionId) setAdvisorOptionId(next)
    if (next !== defaultAdvisorOptionId) onAdvisorOptionChange(next)
  }, [advisorOptionId, defaultAdvisorOptionId, modelOptions, onAdvisorOptionChange])

  const targetOptions = useMemo(() => {
    const external = new Map<string, string>()
    history.forEach((run) => {
      if (run.external_agent?.id) external.set(run.external_agent.id, run.external_agent.name)
    })
    return [
      { value: "all", label: "全部实验对象" },
      { value: "builtin", label: "内置参考宿主与标准套件" },
      ...[...external.entries()].map(([value, name]) => ({ value, label: `外部 Agent · ${name}` })),
    ]
  }, [history])

  const filteredRuns = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return history.filter((run) => {
      const targetMatches = target === "all"
        || (target === "builtin" && run.source_kind !== "external_agent")
        || run.external_agent?.id === target
      if (!targetMatches) return false
      if (!normalized) return true
      return [
        run.batch_id,
        run.suite_name,
        run.external_agent?.name || "",
        ...run.tasks.flatMap((task) => [task.task_id, task.host, task.mode]),
      ].join(" ").toLowerCase().includes(normalized)
    })
  }, [history, query, target])

  const filteredTasks = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return filteredRuns.flatMap((run) => {
      const runMatches = !normalized || [run.batch_id, run.suite_name, run.external_agent?.name || ""].join(" ").toLowerCase().includes(normalized)
      return run.tasks
        .filter((task) => runMatches || [task.task_id, task.host, task.mode].join(" ").toLowerCase().includes(normalized))
        .map((task) => ({ run, task }))
    })
  }, [filteredRuns, query])

  const judgements = useMemo(
    () => filteredTasks.flatMap(({ task }) => task.judgements).filter((judgement) => layer === "all" || layerOf(judgement) === layer),
    [filteredTasks, layer],
  )
  const evaluable = judgements.filter((judgement) => !nonEvaluable.includes(verdictOf(judgement)))
  const silentFailures = judgements.filter((judgement) => verdictOf(judgement) === "silent_failure").length
  const explicitFailures = judgements.filter((judgement) => verdictOf(judgement) === "explicit_failure").length
  const contractViolations = judgements.filter((judgement) => verdictOf(judgement) === "contract_violation").length
  const independentUnknownCompleted = judgements.filter((judgement) => {
    const evidence = evidenceOf(judgement)
    return layerOf(judgement) === "model" && verdictOf(judgement) === "completed"
      && evidence.state_claim_protocol === "independent_judgment_v1"
      && evidence.expected_state_claim === "unknown"
  }).length
  const harnessErrors = filteredTasks.filter(({ task }) => task.status === "failed").length
  const distribution = verdictOrder.map((verdict) => ({
    verdict,
    name: verdictLabels[verdict],
    value: judgements.filter((judgement) => verdictOf(judgement) === verdict).length,
    color: verdictColors[verdict],
  })).filter((item) => item.value > 0)

  const taskAggregates = useMemo(() => {
    const groups = new Map<string, TaskAggregate>()
    filteredTasks.forEach(({ task }) => {
      const protocol = protocolOfTask(task)
      const key = `${task.task_id}|${task.host}|${task.mode}|${protocol}`
      const group = groups.get(key) || {
        taskId: task.task_id,
        host: task.host,
        mode: task.mode,
        protocol,
        total: 0,
        completed: 0,
        failed: 0,
        verdicts: {},
      }
      group.total += 1
      if (task.status === "completed") group.completed += 1
      if (task.status === "failed") group.failed += 1
      task.judgements.forEach((judgement) => {
        if (layer !== "all" && layerOf(judgement) !== layer) return
        const verdict = verdictOf(judgement)
        group.verdicts[verdict] = (group.verdicts[verdict] || 0) + 1
      })
      groups.set(key, group)
    })
    return [...groups.values()].sort((a, b) => (b.verdicts.silent_failure || 0) - (a.verdicts.silent_failure || 0) || b.failed - a.failed || a.taskId.localeCompare(b.taskId))
  }, [filteredTasks, layer])

  const trendData = useMemo(() => filteredRuns.slice(0, 8).reverse().map((run) => {
    const tasks = filteredTasks.filter((item) => item.run.batch_id === run.batch_id)
    const runJudgements = tasks.flatMap(({ task }) => task.judgements).filter((judgement) => layer === "all" || layerOf(judgement) === layer)
    const runEvaluable = runJudgements.filter((judgement) => !nonEvaluable.includes(verdictOf(judgement))).length
    const silent = runJudgements.filter((judgement) => verdictOf(judgement) === "silent_failure").length
    const contract = runJudgements.filter((judgement) => verdictOf(judgement) === "contract_violation").length
    return {
      batchId: run.batch_id,
      label: shortBatchTime(run.started_at),
      fullName: run.external_agent?.name || run.suite_name,
      date: formatDateTime(run.started_at),
      silentRate: percentNumber(silent, runEvaluable),
      contractRate: percentNumber(contract, runEvaluable),
      evaluable: runEvaluable,
    }
  }), [filteredRuns, filteredTasks, layer])

  const riskData = useMemo(() => taskAggregates.slice(0, 6).map((group) => ({
    name: group.taskId.length > 24 ? `${group.taskId.slice(0, 22)}…` : group.taskId,
    fullName: `${group.taskId} · ${group.host} · ${group.mode}`,
    silent: group.verdicts.silent_failure || 0,
    contract: group.verdicts.contract_violation || 0,
    explicit: group.verdicts.explicit_failure || 0,
  })), [taskAggregates])

  const insights = useMemo<AnalysisInsight[]>(() => {
    const result: AnalysisInsight[] = []
    if (!filteredTasks.length) return [{ tone: "info", title: "当前范围没有任务", detail: "调整筛选条件，或先在实验页运行兼容任务。" }]
    if (harnessErrors) {
      result.push({ tone: "warning", title: `${harnessErrors} 个任务需要先修复实验设施`, detail: "Harness 错误不计作 Agent 的有效故障行为样本；应先检查适配器、模型请求或产物复算，再比较行为表现。" })
    }
    if (silentFailures) {
      const highest = [...taskAggregates].sort((a, b) => (b.verdicts.silent_failure || 0) - (a.verdicts.silent_failure || 0))[0]
      result.push({ tone: "risk", title: `沉默失败占可判定结果 ${percent(silentFailures, evaluable.length)}`, detail: `共 ${silentFailures} 条；最集中于 ${highest.taskId} · ${highest.host} · ${highest.mode}（${highest.verdicts.silent_failure || 0} 条）。这里只能定位集中位置，根因需回到原始轨迹复核。` })
    }
    if (contractViolations) {
      result.push({ tone: "risk", title: `发现 ${contractViolations} 条契约违反`, detail: "这些结果表示实际行为与预注册后置条件不一致，应优先核对对应任务的事件证据，而不是调整 Oracle 让结果变绿。" })
    }
    if (explicitFailures) {
      result.push({ tone: "warning", title: `显式失败占可判定结果 ${percent(explicitFailures, evaluable.length)}`, detail: `共 ${explicitFailures} 条。显式失败至少暴露了错误，而不是静默宣称成功；是否属于故障任务的预期表现，仍需结合该任务的 expected_behavior 判断。` })
    }
    if (trendData.length >= 2) {
      const latest = trendData[trendData.length - 1]
      const previous = trendData[trendData.length - 2]
      if (latest.evaluable && previous.evaluable) {
        const delta = Number((latest.silentRate - previous.silentRate).toFixed(1))
        result.push({
          tone: delta > 0 ? "risk" : delta < 0 ? "good" : "info",
          title: `最近批次沉默失败率${delta > 0 ? "上升" : delta < 0 ? "下降" : "持平"} ${Math.abs(delta).toFixed(1)} 个百分点`,
          detail: `由 ${previous.silentRate}%（${previous.evaluable} 条可判定）变为 ${latest.silentRate}%（${latest.evaluable} 条可判定）。单批波动不能证明修改有效，需要更多同条件样本。`,
        })
      }
    }
    const insufficient = judgements.filter((judgement) => verdictOf(judgement) === "inconclusive").length
    if (insufficient) {
      result.push({ tone: "info", title: `${insufficient} 条判定证据不足`, detail: "它们已从可判定比例的分母排除。若占比较高，应补充观察点或重跑，不应强行计入成功或失败。" })
    }
    if (independentUnknownCompleted) {
      result.push({ tone: "info", title: `${independentUnknownCompleted} 条 completed 仅表示符合信息不足预注册`, detail: "独立判断协议下，预注册与实际声明均为 unknown 时判 completed；这不是业务成功，也不能与默认协议混在同一任务聚合中。" })
    }
    if (!silentFailures && !contractViolations && !explicitFailures && evaluable.length) {
      result.push({ tone: "good", title: "当前可判定结果均符合预注册", detail: `结论只覆盖 ${evaluable.length} 条可判定 Oracle，不代表业务成功，也不代表其他任务、模型或未测故障同样符合预期。` })
    }
    if (result.length === 0) {
      result.push({ tone: "info", title: "暂无可判定行为结论", detail: "当前只有不适用或未知判定；请调整 Oracle 层级，或检查实验是否已产生有效证据。" })
    }
    return result.slice(0, 5)
  }, [contractViolations, evaluable.length, explicitFailures, filteredTasks.length, harnessErrors, independentUnknownCompleted, judgements, silentFailures, taskAggregates, trendData])

  const selections = useMemo(() => filteredTasks.map(({ run, task }) => ({ batch_id: run.batch_id, task_id: task.task_id })), [filteredTasks])
  const scopeKey = useMemo(() => JSON.stringify({ selections, layer }), [selections, layer])
  const targetLabel = targetOptions.find((option) => option.value === target)?.label || target
  const layerLabel = layer === "all" ? "全部层级" : layer === "framework" ? "框架层" : "模型层"
  const scopeLabel = `${targetLabel}；检索：${query.trim() || "无"}；Oracle：${layerLabel}`
  const hasUnfinished = filteredTasks.some(({ task }) => task.status === "pending" || task.status === "running")
  const llmUnavailableReason = !selections.length
    ? "当前没有可分析任务"
    : hasUnfinished
      ? "请等待当前任务全部结束"
      : selections.length > 300
        ? "单次最多分析 300 个任务，请缩小筛选范围"
        : !advisorOptionId
          ? "尚未配置带 chat 能力的模型"
          : ""
  const llmIsCurrent = llmAnalysis?.scopeKey === scopeKey

  async function generateAnalysis() {
    if (llmUnavailableReason || analysisLoading) return
    const requestScopeKey = scopeKey
    const requestScopeLabel = scopeLabel
    setAnalysisLoading(true)
    setAnalysisError("")
    try {
      const result = await api.generateAnalysis(selections, layer, advisorOptionId)
      setLlmAnalysis({ result, scopeKey: requestScopeKey, scopeLabel: requestScopeLabel })
    } catch (reason) {
      setAnalysisError(reason instanceof Error ? reason.message : "LLM 实验分析生成失败")
    } finally {
      setAnalysisLoading(false)
    }
  }

  function downloadAnalysis() {
    const lines = [
      "# FaultLattice 实验分析",
      "",
      `生成时间：${formatDateTime(new Date().toISOString())}`,
      `实验对象：${targetLabel}`,
      `检索条件：${query.trim() || "无"}`,
      `Oracle 层级：${layerLabel}`,
      "",
      "## 汇总",
      "",
      `- 批次：${filteredRuns.length}`,
      `- 任务：${filteredTasks.length}；执行完成 ${filteredTasks.filter(({ task }) => task.status === "completed").length}；Harness 错误 ${harnessErrors}`,
      `- 可判定 Oracle：${evaluable.length} / ${judgements.length}`,
      `- 沉默失败：${silentFailures}；占可判定结果 ${percent(silentFailures, evaluable.length)}`,
      `- 显式失败：${explicitFailures}；占可判定结果 ${percent(explicitFailures, evaluable.length)}`,
      `- 契约违反：${contractViolations}`,
      "",
      "## 规则分析结果",
      "",
      ...insights.map((insight) => `- **${insight.title}**：${insight.detail}`),
      "",
      "## Oracle 判定分布",
      "",
      "| 判定 | 数量 | 占当前判定 |",
      "| --- | ---: | ---: |",
      ...distribution.map((item) => `| ${item.name} | ${item.value} | ${percent(item.value, judgements.length)} |`),
      "",
      "## 最近批次趋势",
      "",
      "| 批次 | 时间 | 可判定 Oracle | 沉默失败率 | 契约违反率 |",
      "| --- | --- | ---: | ---: | ---: |",
      ...trendData.map((item) => `| \`${item.batchId}\` | ${item.date} | ${item.evaluable} | ${item.silentRate}% | ${item.contractRate}% |`),
      "",
      "## 任务对比",
      "",
      "| 任务 | 宿主 | 模式 | 状态声明协议 | 执行完成 | Harness 错误 | 符合预注册 | 显式失败 | 沉默失败 | 契约违反 | 证据不足 |",
      "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
      ...taskAggregates.map((group) => `| ${markdownCell(group.taskId)} | ${markdownCell(group.host)} | ${group.mode} | ${group.protocol} | ${group.completed}/${group.total} | ${group.failed} | ${group.verdicts.completed || 0} | ${group.verdicts.explicit_failure || 0} | ${group.verdicts.silent_failure || 0} | ${group.verdicts.contract_violation || 0} | ${group.verdicts.inconclusive || 0} |`),
      "",
      "## 批次索引",
      "",
      ...filteredRuns.map((run) => `- ${formatDateTime(run.started_at)} · ${run.suite_name} · ${statusLabels[run.status]} · \`${run.batch_id}\``),
      "",
      "> 执行完成不等于被测 Agent 没有缺陷；本报告只汇总已有真实历史，不重新执行或修改 Oracle。",
      "",
    ]
    if (llmAnalysis && llmIsCurrent) {
      lines.push(
        "## 大模型辅助分析",
        "",
        `- 模型：${llmAnalysis.result.model_id}`,
        `- 生成时间：${formatDateTime(llmAnalysis.result.generated_at)}`,
        "",
        llmAnalysis.result.content,
        "",
      )
    }
    downloadMarkdown(`faultlattice-analysis-${new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-")}.md`, lines.join("\n"))
  }

  return (
    <div className="view-stack analytics-subview">
      <section className="analysis-panel analysis-filters" aria-label="分析筛选">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索批次、任务、宿主或套件"
          aria-label="搜索分析历史"
        />
        <Select value={target} onChange={setTarget} options={targetOptions} aria-label="筛选实验对象" />
        <Select
          value={layer}
          onChange={setLayer}
          aria-label="筛选 Oracle 层级"
          options={[{ value: "all", label: "全部 Oracle 层级" }, { value: "framework", label: "框架层" }, { value: "model", label: "模型层" }]}
        />
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新历史</Button>
        <Button type="primary" icon={<DownloadOutlined />} disabled={!filteredRuns.length} onClick={downloadAnalysis}>下载分析 Markdown</Button>
      </section>

      {error && <Alert type="error" showIcon title="实验分析读取失败" description={error} />}
      {loading && !history.length ? <div className="view-loading"><Spin size="large" description="正在读取真实实验历史" /></div> : !history.length ? (
        <Empty description="尚无实验历史；请先在实验页运行一个兼容任务" />
      ) : (
        <>
          <div className="analysis-metrics">
            <div><strong>{filteredRuns.length}</strong><span>匹配批次</span><small>{filteredTasks.length} 个任务</small></div>
            <div><strong>{filteredTasks.filter(({ task }) => task.status === "completed").length}</strong><span>任务执行完成</span><small>不代表 Agent 无缺陷</small></div>
            <div><strong>{evaluable.length}<small>/{judgements.length}</small></strong><span>可判定 Oracle</span><small>排除证据不足与不适用</small></div>
            <div className={silentFailures ? "is-risk" : ""}><strong>{silentFailures}</strong><span>沉默失败</span><small>{percent(silentFailures, evaluable.length)} · 当前可判定结果</small></div>
          </div>

          {independentUnknownCompleted > 0 && <Alert type="info" showIcon title={`${independentUnknownCompleted} 条 completed 表示符合信息不足预注册`} description="独立判断协议下，预注册与实际声明均为 unknown 时得到 completed；这不是业务成功。任务对比已按协议拆分，不与默认强指令协议混合。" />}
          {harnessErrors > 0 && <Alert type="warning" showIcon title={`当前范围有 ${harnessErrors} 个 Harness 执行错误`} description="这些任务不计作被测 Agent 的有效故障行为样本，请回到实验页检查适配器、模型或配置错误。" />}

          <section className="analysis-panel analysis-insights" aria-labelledby="rule-analysis-heading">
            <div className="section-heading"><div><span className="section-kicker">DETERMINISTIC FINDINGS</span><h2 id="rule-analysis-heading">数据分析结果</h2></div><span>固定规则 · 可复算</span></div>
            <div className="analysis-insight-grid">
              {insights.map((insight) => (
                <article className={`analysis-insight insight-${insight.tone}`} key={`${insight.title}-${insight.detail}`}>
                  {insight.tone === "risk" || insight.tone === "warning" ? <AlertOutlined /> : insight.tone === "good" ? <CheckCircleOutlined /> : <InfoCircleOutlined />}
                  <div><h3>{insight.title}</h3><p>{insight.detail}</p></div>
                </article>
              ))}
            </div>
          </section>

          <div className="analysis-chart-grid">
            <section className="analysis-panel analysis-chart-card" aria-labelledby="verdict-chart-heading">
              <div className="section-heading"><div><span className="section-kicker">ORACLE COMPOSITION</span><h2 id="verdict-chart-heading">判定构成</h2></div><span>{judgements.length} 条判定</span></div>
              {!distribution.length ? <Empty description="当前筛选没有 Oracle 判定" /> : (
                <div className="analysis-chart analysis-pie-chart" role="img" aria-label={distribution.map((item) => `${item.name} ${item.value} 条`).join("，")}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={distribution} dataKey="value" nameKey="name" innerRadius="54%" outerRadius="78%" paddingAngle={3} stroke="none" isAnimationActive={motionEnabled} animationDuration={650}>
                        {distribution.map((item) => <Cell key={item.verdict} fill={item.color} />)}
                      </Pie>
                      <Tooltip content={<AnalysisTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="analysis-chart-legend">
                    {distribution.map((item) => <span key={item.verdict}><i style={{ background: item.color }} />{item.name}<b>{item.value}</b></span>)}
                  </div>
                </div>
              )}
            </section>

            <section className="analysis-panel analysis-chart-card" aria-labelledby="trend-chart-heading">
              <div className="section-heading"><div><span className="section-kicker">BATCH TREND</span><h2 id="trend-chart-heading">最近批次风险趋势</h2></div><span>最多 8 个批次</span></div>
              {!trendData.some((item) => item.evaluable) ? <Empty description="当前批次没有可判定结果" /> : (
                <div className="analysis-chart" role="img" aria-label="最近批次沉默失败率与契约违反率折线图">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData} margin={{ top: 12, right: 16, left: -16, bottom: 0 }}>
                      <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 5" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: "var(--color-muted)", fontSize: 11 }} axisLine={{ stroke: "var(--color-border)" }} tickLine={false} />
                      <YAxis unit="%" domain={[0, 100]} tick={{ fill: "var(--color-muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <Tooltip content={<AnalysisTooltip />} />
                      <Legend formatter={(value) => <span className="chart-legend-label">{value}</span>} />
                      <Line name="沉默失败率" unit="%" dataKey="silentRate" stroke="#fb7185" strokeWidth={2.5} dot={{ r: 4, fill: "#fb7185", strokeWidth: 0 }} activeDot={{ r: 7 }} isAnimationActive={motionEnabled} animationDuration={700} />
                      <Line name="契约违反率" unit="%" dataKey="contractRate" stroke="#f97316" strokeWidth={2} dot={{ r: 3, fill: "#f97316", strokeWidth: 0 }} activeDot={{ r: 6 }} isAnimationActive={motionEnabled} animationDuration={700} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </section>
          </div>

          <section className="analysis-panel analysis-chart-card" aria-labelledby="risk-chart-heading">
            <div className="section-heading"><div><span className="section-kicker">TASK RISK PROFILE</span><h2 id="risk-chart-heading">任务风险对比</h2></div><span>显示前 {Math.min(6, riskData.length)} 个任务组合</span></div>
            {!riskData.some((item) => item.silent || item.contract || item.explicit) ? <Empty description="当前任务没有显式失败、沉默失败或契约违反" /> : (
              <div className="analysis-chart analysis-risk-chart" role="img" aria-label="按任务、宿主与模式聚合的失败判定横向柱状图">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={riskData} layout="vertical" margin={{ top: 4, right: 20, left: 16, bottom: 4 }}>
                    <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 5" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} tick={{ fill: "var(--color-muted)", fontSize: 11 }} axisLine={{ stroke: "var(--color-border)" }} tickLine={false} />
                    <YAxis type="category" dataKey="name" width={170} tick={{ fill: "var(--color-muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<AnalysisTooltip />} cursor={{ fill: "var(--color-raised)", opacity: 0.45 }} />
                    <Legend formatter={(value) => <span className="chart-legend-label">{value}</span>} />
                    <Bar name="显式失败" dataKey="explicit" stackId="risk" fill="#fbbf24" isAnimationActive={motionEnabled} animationDuration={600} />
                    <Bar name="沉默失败" dataKey="silent" stackId="risk" fill="#fb7185" isAnimationActive={motionEnabled} animationDuration={700} />
                    <Bar name="契约违反" dataKey="contract" stackId="risk" fill="#f97316" radius={[0, 4, 4, 0]} isAnimationActive={motionEnabled} animationDuration={800} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          <section className="analysis-panel analysis-llm-panel" aria-labelledby="llm-analysis-heading">
            <div className="section-heading analysis-llm-heading">
              <div><span className="section-kicker">LLM ASSISTED ANALYSIS</span><h2 id="llm-analysis-heading">大模型辅助分析</h2><p>只发送当前任务的聚合数量、状态和判定，不发送完整轨迹、源码或密钥。根因定位仍需查看单次任务证据。</p></div>
              <RobotOutlined aria-hidden="true" />
            </div>
            <div className="analysis-llm-controls">
              <label><span>分析模型</span><Select value={advisorOptionId || undefined} onChange={(value) => { setAdvisorOptionId(value); onAdvisorOptionChange(value) }} options={modelOptions.map((option) => ({ value: option.id, label: `${option.label} · ${option.model_id}` }))} placeholder="没有可用对话模型" disabled={!modelOptions.length || analysisLoading} aria-label="实验分析模型" /></label>
              <Button type="primary" icon={<RobotOutlined />} loading={analysisLoading} disabled={Boolean(llmUnavailableReason)} onClick={() => void generateAnalysis()}>{llmAnalysis ? "按当前范围重新分析" : "生成模型分析"}</Button>
              {llmAnalysis && <MarkdownDownloadButton content={llmDocument(llmAnalysis)} filename={`faultlattice-llm-analysis-${llmAnalysis.result.generated_at.replaceAll(":", "-").replaceAll(".", "-")}.md`} />}
            </div>
            <small className="analysis-llm-reason">{llmUnavailableReason || `将分析 ${selections.length} 个任务；模型输出只供人工复核，可单独下载，也会并入当前分析 Markdown。`}</small>
            {modelError && <Alert type="warning" showIcon title="模型目录不可用" description={modelError} />}
            {analysisError && <Alert type="error" showIcon title="模型分析生成失败" description={analysisError} />}
            {analysisLoading && <div className="analysis-generating"><Spin size="small" /><span>所选模型正在阅读聚合证据并生成中文分析，请不要重复提交。</span></div>}
            {llmAnalysis && !llmIsCurrent && <Alert type="info" showIcon title="以下是上一筛选范围的分析" description={`原范围：${llmAnalysis.scopeLabel}。筛选变化不会自动消耗 Token；确认后可重新生成。`} />}
            {llmAnalysis && (
              <div className="analysis-llm-result">
                <div className="analysis-result-meta"><Tag color="blue">{llmAnalysis.result.model_id}</Tag><span>{formatDateTime(llmAnalysis.result.generated_at)}</span></div>
                <div className="document-view compact analysis-llm-output" tabIndex={0} aria-label="大模型实验分析结果，可滚动阅读">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{llmAnalysis.result.content}</ReactMarkdown>
                </div>
              </div>
            )}
          </section>

          <div className="analysis-grid">
            <section className="analysis-panel">
              <div className="section-heading"><div><span className="section-kicker">ORACLE DISTRIBUTION</span><h2>判定明细</h2></div><span>{judgements.length} 条判定</span></div>
              {!distribution.length ? <Empty description="当前筛选没有 Oracle 判定" /> : (
                <div className="verdict-distribution">
                  {distribution.map((item) => (
                    <div className={`verdict-row verdict-${item.verdict}`} key={item.verdict}>
                      <div><strong>{item.name}</strong><span>{item.value} · {percent(item.value, judgements.length)}</span></div>
                      <div className="verdict-track" aria-label={`${item.name} ${percent(item.value, judgements.length)}`}><span style={{ width: `${item.value / judgements.length * 100}%` }} /></div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="analysis-panel">
              <div className="section-heading"><div><span className="section-kicker">RECENT BATCHES</span><h2>最近批次</h2></div><span>点击查看原始过程</span></div>
              {!filteredRuns.length ? <Empty description="没有匹配批次" /> : (
                <div className="analysis-batch-list">
                  {filteredRuns.slice(0, 8).map((run) => (
                    <button type="button" key={run.batch_id} onClick={() => navigate(`/experiments?batch=${encodeURIComponent(run.batch_id)}`)}>
                      <span><strong>{run.external_agent?.name || run.suite_name}</strong><small>{formatDateTime(run.started_at)}</small></span>
                      <span><Tag color={run.status === "completed" ? "success" : run.status === "failed" ? "error" : "processing"}>{statusLabels[run.status]}</Tag><ArrowRightOutlined /></span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className="analysis-panel">
            <div className="section-heading"><div><span className="section-kicker">TASK COMPARISON</span><h2>任务对比</h2></div><span>{taskAggregates.length} 个任务与宿主组合</span></div>
            {!taskAggregates.length ? <Empty description="没有匹配任务" /> : (
              <div className="analysis-table-wrap">
                <table className="analysis-table">
                  <thead><tr><th>任务 / 宿主</th><th>状态声明协议</th><th>执行完成</th><th>Harness 错误</th><th>符合预注册</th><th>显式失败</th><th>沉默失败</th><th>契约违反</th><th>证据不足</th></tr></thead>
                  <tbody>
                    {taskAggregates.map((group) => (
                      <tr key={`${group.taskId}|${group.host}|${group.mode}|${group.protocol}`}>
                        <td><strong>{group.taskId}</strong><span>{group.host} · {group.mode}</span></td>
                        <td><Tag color={group.protocol === "independent_judgment_v1" ? "purple" : "default"}>{protocolLabel(group.protocol)}</Tag><span><code>{group.protocol}</code></span></td>
                        <td>{group.completed}/{group.total}</td>
                        <td>{group.failed || "—"}</td>
                        <td>{group.verdicts.completed || 0}</td>
                        <td>{group.verdicts.explicit_failure || 0}</td>
                        <td className={group.verdicts.silent_failure ? "risk-number" : ""}>{group.verdicts.silent_failure || 0}</td>
                        <td>{group.verdicts.contract_violation || 0}</td>
                        <td>{group.verdicts.inconclusive || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
