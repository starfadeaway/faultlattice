import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  BulbOutlined,
  CheckCircleOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons"
import { Alert, Button, Collapse, Empty, Input, Progress, Select, Spin, Tag, Tooltip } from "antd"
import ReactMarkdown from "react-markdown"
import { useNavigate } from "react-router"
import remarkGfm from "remark-gfm"
import { api } from "../api"
import { ExperimentTargetPanel } from "../components/ExperimentTargetPanel"
import { MarkdownDownloadButton } from "../components/MarkdownDownloadButton"
import type { ExperimentSuite, ExternalAgent, ModelOption, SuiteRun, SuiteTaskResult } from "../types"
import { downloadMarkdown } from "../utils/downloadMarkdown"
import { formatDateTime } from "../utils/dateTime"

const statusText = {
  pending: "等待",
  running: "运行中",
  completed: "已完成",
  failed: "执行错误",
}

function statusColor(status: string): string {
  if (status === "completed") return "success"
  if (status === "failed") return "error"
  if (status === "running") return "processing"
  return "default"
}

function reasoningModeLabel(mode: string | null | undefined, modelId = ""): string {
  if (mode === "enabled") return "思考模式 · 原始思考字段回传"
  if (mode === "disabled") return "非思考模式 · 显式实验条件"
  if (mode === "default" && modelId.startsWith("deepseek-")) return "思考模式 · 提供方默认开启"
  return "提供方默认"
}

function eventTitle(event: Record<string, unknown>): string {
  const type = String(event.event_type || "event")
  const phase = event.m3_phase === "prefix" ? "真实前缀" : event.m3_phase === "continuation" ? "故障后续跑" : ""
  const tool = event.tool_name ? ` · ${String(event.tool_name)}` : ""
  const verdict = event.verdict ? ` · ${String(event.verdict)}` : ""
  return `${String(event.step_id || event.seq || "TRACE")} · ${type}${phase ? ` · ${phase}` : ""}${tool}${verdict}`
}

function eventText(event: Record<string, unknown>, nextEvent?: Record<string, unknown>): string {
  if (event.event_type === "model_output") {
    const content = typeof event.content === "string" ? event.content : ""
    if (content) return content
    const hasReasoning = typeof event.reasoning_content === "string" && event.reasoning_content.length > 0
    const hasToolCall = nextEvent?.event_type === "tool_call"
    if (!hasReasoning && !hasToolCall) {
      return "（异常空响应：本轮无正文、无思考记录，下一事件也不是工具调用；请检查模型响应）"
    }
    return `（本轮无正文${hasReasoning ? " · 已记录思考内容" : ""}${hasToolCall ? " · 下一事件为工具调用" : ""}）`
  }
  if (event.event_type === "tool_call") return JSON.stringify(event.arguments, null, 2)
  if (event.event_type === "tool_result") {
    return event.error ? String(event.error) : JSON.stringify(event.result, null, 2)
  }
  if (event.event_type === "injection") {
    return JSON.stringify({
      original: event.original,
      replacement: event.replacement,
      applied: event.applied,
      ...(event.timeout_mode ? {
        timeout_mode: event.timeout_mode,
        timeout_seconds: event.timeout_seconds,
        elapsed_seconds: event.elapsed_seconds,
        worker_pid: event.worker_pid,
        process_terminated: event.process_terminated,
      } : {}),
    }, null, 2)
  }
  if (event.event_type === "run_end") return String(event.final_answer || event.framework_outcome || "")
  return JSON.stringify(event, null, 2)
}

interface ExperimentsViewProps {
  refreshInterval?: number
  defaultAdvisorOptionId: string
  onAdvisorOptionChange: (optionId: string) => void
  completionNotifications: boolean
  autoScrollResults: boolean
}

export function ExperimentsView({
  refreshInterval = 800,
  defaultAdvisorOptionId,
  onAdvisorOptionChange,
  completionNotifications,
  autoScrollResults,
}: ExperimentsViewProps) {
  const [suites, setSuites] = useState<ExperimentSuite[]>([])
  const [history, setHistory] = useState<SuiteRun[]>([])
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([])
  const [agents, setAgents] = useState<ExternalAgent[]>([])
  const [selectedSuiteId, setSelectedSuiteId] = useState("")
  const [selectedBatchId, setSelectedBatchId] = useState("")
  const [selectedTaskId, setSelectedTaskId] = useState("")
  const [targetId, setTargetId] = useState("builtin")
  const [externalTaskPath, setExternalTaskPath] = useState("")
  const [historyQuery, setHistoryQuery] = useState("")
  const [advisorOptionId, setAdvisorOptionId] = useState(defaultAdvisorOptionId)
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState("")
  const [adviceLoading, setAdviceLoading] = useState("")
  const [error, setError] = useState("")
  const initialLoad = useRef(false)
  const advisorOptionRef = useRef(defaultAdvisorOptionId)
  const advisorOptionChangeRef = useRef(onAdvisorOptionChange)
  const notifiedBatches = useRef(new Set<string>())
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setError("")
    try {
      const [suiteData, historyData, modelData, agentData] = await Promise.all([
        api.experimentSuites(),
        api.experimentHistory(),
        // 旧后端尚未热加载模型目录时，套件与历史仍必须可用。
        api.experimentModels().catch(() => []),
        api.externalAgents(),
      ])
      setSuites(suiteData)
      setHistory(historyData)
      setModelOptions(modelData)
      setAgents(agentData)
      const nextAdvisorOptionId = modelData.some((option) => option.id === advisorOptionRef.current)
        ? advisorOptionRef.current
        : modelData[0]?.id || ""
      advisorOptionRef.current = nextAdvisorOptionId
      setAdvisorOptionId(nextAdvisorOptionId)
      advisorOptionChangeRef.current(nextAdvisorOptionId)
      setSelectedSuiteId((current) => current || suiteData[0]?.id || "")
      const requestedBatch = new URLSearchParams(window.location.search).get("batch")
      const requestedRun = historyData.find((run) => run.batch_id === requestedBatch)
      const requestedAgent = requestedRun?.external_agent?.id
      setSelectedBatchId((current) => current || (
        requestedRun ? requestedRun.batch_id : historyData[0]?.batch_id || ""
      ))
      setTargetId((current) => {
        if (current !== "builtin" && agentData.some((agent) => agent.id === current && agent.status === "ready")) return current
        if (requestedAgent && agentData.some((agent) => agent.id === requestedAgent && agent.status === "ready")) return requestedAgent
        return "builtin"
      })
      if (requestedRun?.source_kind === "external_agent") {
        setExternalTaskPath(requestedRun.tasks[0]?.task_path || "")
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "实验数据读取失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (initialLoad.current) return
    initialLoad.current = true
    void load()
  }, [load])

  useEffect(() => {
    advisorOptionRef.current = advisorOptionId
    advisorOptionChangeRef.current = onAdvisorOptionChange
  }, [advisorOptionId, onAdvisorOptionChange])

  const selectedRun = history.find((run) => run.batch_id === selectedBatchId) || null
  const running = selectedRun?.status === "running"

  useEffect(() => {
    if (!selectedBatchId || !running) return
    const timer = window.setInterval(() => {
      void api.experimentDetail(selectedBatchId).then((next) => {
        setHistory((current) => current.map((item) => item.batch_id === next.batch_id ? next : item))
        if (next.status !== "running") {
          window.clearInterval(timer)
          if (completionNotifications && "Notification" in window && Notification.permission === "granted" && !notifiedBatches.current.has(next.batch_id)) {
            notifiedBatches.current.add(next.batch_id)
            const failed = next.status === "failed"
            new Notification(failed ? "FaultLattice 实验执行终止" : "FaultLattice 实验执行完成", {
              body: failed
                ? `${next.suite_name}：出现 Harness 执行错误，请查看任务详情。`
                : `${next.suite_name}：${next.completed_tasks}/${next.total_tasks} 个任务执行完成，请查看 Oracle 判定。`,
              tag: `faultlattice-${next.batch_id}`,
            })
          }
        }
      }).catch((reason) => {
        setError(reason instanceof Error ? reason.message : "运行进度读取失败")
        window.clearInterval(timer)
      })
    }, refreshInterval)
    return () => window.clearInterval(timer)
  }, [selectedBatchId, running, refreshInterval, completionNotifications])

  const readyAgents = useMemo(() => agents.filter((agent) => agent.status === "ready"), [agents])
  const selectedAgent = readyAgents.find((agent) => agent.id === targetId) || null
  const selectedExternalTask = selectedAgent?.compatible_tasks.find((task) => task.path === externalTaskPath)
    || selectedAgent?.compatible_tasks[0]
    || null
  const selectedSuite = suites.find((suite) => suite.id === selectedSuiteId) || null
  const selectedTask = selectedRun?.tasks.find((task) => task.task_id === selectedTaskId)
    || selectedRun?.tasks[0]
    || null
  const selectedAdvisor = modelOptions.find((option) => option.id === advisorOptionId) || null
  const advisorConfigured = selectedAdvisor !== null
  const advisorModelId = selectedAdvisor?.model_id || null
  const progress = useMemo(() => {
    if (!selectedRun?.total_tasks) return 0
    return Math.round(selectedRun.completed_tasks / selectedRun.total_tasks * 100)
  }, [selectedRun])
  const visibleHistory = useMemo(() => {
    const query = historyQuery.trim().toLowerCase()
    if (!query) return history
    return history.filter((run) => [
      run.suite_name,
      run.batch_id,
      run.external_agent?.name || "",
      ...run.tasks.map((task) => task.task_id),
    ].join(" ").toLowerCase().includes(query))
  }, [history, historyQuery])

  function acceptRun(run: SuiteRun) {
    setHistory((current) => [run, ...current.filter((item) => item.batch_id !== run.batch_id)])
    setSelectedBatchId(run.batch_id)
    setSelectedTaskId("")
    if (!autoScrollResults) return
    window.requestAnimationFrame(() => {
      document.getElementById("experiment-results")?.scrollIntoView({
        behavior: document.documentElement.dataset.motion === "off" ? "auto" : "smooth",
        block: "start",
      })
    })
  }

  function selectTarget(value: string) {
    setTargetId(value)
    const agent = readyAgents.find((item) => item.id === value)
    setExternalTaskPath(agent?.compatible_tasks[0]?.path || "")
    setError("")
  }

  async function startSuite(suite: ExperimentSuite) {
    setStarting(suite.id)
    setError("")
    try {
      acceptRun(await api.runSuite(suite.id, suite.requires_model ? advisorOptionId || undefined : undefined))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "套件启动失败")
    } finally {
      setStarting("")
    }
  }

  async function startExternalTask() {
    if (!selectedAgent || !selectedExternalTask) return
    setStarting(`external:${selectedAgent.id}`)
    setError("")
    try {
      acceptRun(await api.runExternalAgent(
        selectedAgent.id,
        selectedExternalTask.path,
        selectedExternalTask.mode === "M3" ? advisorOptionId || undefined : undefined,
      ))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "外部 Agent 测试启动失败")
    } finally {
      setStarting("")
    }
  }

  async function generateAdvice() {
    if (!selectedRun || !selectedTask || !advisorOptionId) return
    const loadingKey = `${selectedRun.batch_id}:${selectedTask.task_id}`
    setAdviceLoading(loadingKey)
    setError("")
    try {
      const result = await api.generateAdvice(selectedRun.batch_id, selectedTask.task_id, advisorOptionId)
      setHistory((current) => current.map((run) => run.batch_id === selectedRun.batch_id ? {
        ...run,
        tasks: run.tasks.map((task) => task.task_id === result.task_id ? {
          ...task,
          advice: result.content,
          advice_model: result.advice_model,
          advice_option_id: result.advice_option_id,
          advice_generated_at: result.advice_generated_at,
        } : task),
      } : run))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "LLM 修改建议生成失败")
    } finally {
      setAdviceLoading("")
    }
  }

  async function saveSuiteReport(batchId: string) {
    setError("")
    try {
      const content = await api.suiteReport(batchId)
      downloadMarkdown(`${batchId}-suite-report.md`, content)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "套件报告下载失败")
    }
  }

  if (loading) return <div className="initial-loading"><Spin size="large" description="正在读取预注册测试项目" /></div>

  return (
    <div className="view-stack experiments-view">
      {error && <Alert type="error" showIcon title={error} />}
      <section className="experiment-intro">
        <div>
          <span className="section-kicker">PREREGISTERED TEST WORKFLOW</span>
          <h2>选择对象与任务，运行后在这里查看结果</h2>
          <p>内置套件和你登记的 Agent 共用同一条真实执行、轨迹、Oracle、报告与建议链。先选实验对象，再选兼容任务；运行前冻结预期，运行后不会倒填判定口径。</p>
        </div>
        <div className="experiment-controls">
          <label>
            <span>真实模型与默认建议模型</span>
            <Select
              value={advisorOptionId || undefined}
              placeholder="尚未配置对话模型"
              disabled={!modelOptions.length}
              options={modelOptions.map((option) => ({
                value: option.id,
                label: `${option.label} · ${option.model_id} · ${reasoningModeLabel(option.reasoning_mode, option.model_id)}`,
              }))}
              onChange={(value) => {
                advisorOptionRef.current = value
                setAdvisorOptionId(value)
                onAdvisorOptionChange(value)
              }}
            />
          </label>
          <small>仅 M3 和修改建议调用对话模型，M0 不会消耗模型 Token。M3 启动时冻结模型、思考模式与采样参数。</small>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新对象、任务与历史</Button>
        </div>
      </section>
      {selectedAdvisor?.reasoning_mode !== "disabled" && selectedAdvisor?.model_id.startsWith("deepseek-") && (
        <Alert type="info" showIcon title="DeepSeek 思考模式已保留" description="M3 将现场建立真实前缀并完整回传 reasoning_content；不会自动关闭思考。若前缀不符合预注册契约或字段缺失，该任务会终止，不会降级后重试。" />
      )}
      {selectedAdvisor?.reasoning_mode === "disabled" && (
        <Alert type="warning" showIcon title="当前是显式非思考实验条件" description="只有本机配置主动指定 disabled 才会使用；结果不得外推为思考模式表现。" />
      )}

      <ExperimentTargetPanel
        agents={readyAgents}
        targetId={targetId}
        taskPath={selectedExternalTask?.path || ""}
        starting={starting === `external:${targetId}`}
        modelConfigured={advisorConfigured}
        onTargetChange={selectTarget}
        onTaskChange={setExternalTaskPath}
        onRun={startExternalTask}
        onOpenIntegrations={(section) => navigate(`/integrations?section=${section}`)}
      />

      {targetId === "builtin" && (
        <section className="suite-catalog" aria-labelledby="suite-catalog-heading">
          <div className="section-heading">
            <div><span className="section-kicker">STEP 2 / STANDARD SUITE</span><h2 id="suite-catalog-heading">选择要自动执行的测试套件</h2></div>
            <span>点击卡片查看任务，再使用卡片下方按钮运行</span>
          </div>
          {!suites.length ? <Empty description="尚未登记实验套件" /> : (
            <div className="suite-grid">
              {suites.map((suite) => (
                <article className={suite.id === selectedSuiteId ? "suite-card active" : "suite-card"} key={suite.id}>
                  <button type="button" className="suite-select" onClick={() => setSelectedSuiteId(suite.id)}>
                    <span className="suite-icon"><ExperimentOutlined /></span>
                    <strong>{suite.name}</strong>
                    <code>{suite.id} / v{suite.version}</code>
                    <p>{suite.description}</p>
                    <span className="suite-tags"><Tag color="blue">内置参考宿主</Tag><Tag>{suite.tasks.length} 个任务</Tag>{suite.requires_model && <Tag color="purple">真实模型 M3</Tag>}</span>
                  </button>
                  <Tooltip title={suite.requires_model && !suite.model_configured ? "请先在本机 .env 配置模型端点与密钥" : "运行前声明已冻结"}>
                    <Button
                      type="primary"
                      icon={<PlayCircleOutlined />}
                      loading={starting === suite.id}
                      disabled={Boolean(starting) || (suite.requires_model && !suite.model_configured)}
                      onClick={() => void startSuite(suite)}
                      block
                    >
                      {suite.requires_model && !suite.model_configured ? "缺少模型配置" : "一键运行套件"}
                    </Button>
                  </Tooltip>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {targetId === "builtin" && selectedSuite && (
        <section className="test-content-panel">
          <div className="section-heading">
            <div><span className="section-kicker">TEST CONTENT</span><h2>{selectedSuite.name} · 测试内容</h2></div>
            <span>预期先于结果登记</span>
          </div>
          <Collapse
            className="task-collapse"
            items={selectedSuite.task_details.map((task) => ({
              key: task.task_id,
              label: <span className="suite-task-label"><strong>{task.task_id}</strong><code>{task.host} · {task.mode}</code></span>,
              children: (
                <div className="task-definition">
                  <p>{task.description}</p>
                  <dl>
                    <div><dt>评价层</dt><dd>{task.target_layers.join(" / ")}</dd></div>
                    <div><dt>故障</dt><dd><code>{task.fault ? `${String(task.fault.injection_point)} / ${String(task.fault.fault_type)} / ${String(task.fault.surface_as)}` : "无故障基线"}</code></dd></div>
                    <div><dt>最低可判定样本</dt><dd>{task.min_evaluable}</dd></div>
                    {task.model && <div><dt>预注册默认模型</dt><dd><code>{task.model.model_id}</code> · {reasoningModeLabel(task.model.reasoning_mode, task.model.model_id)} · {JSON.stringify(task.model.sampling_params)}<small>启动前可在上方选择已配置模型；实际模型、思考模式与最终采样参数会冻结进本次运行。</small></dd></div>}
                  </dl>
                  <strong>预期行为</strong><p>{task.expected_behavior}</p>
                  <strong>后置条件</strong><pre>{JSON.stringify(task.expected_postcondition, null, 2)}</pre>
                </div>
              ),
            }))}
          />
        </section>
      )}

      <section className="process-panel" id="experiment-results">
        <div className="section-heading">
          <div><span className="section-kicker">RESULTS / LIVE TRACE</span><h2>查看运行过程与结果</h2></div>
          {selectedRun && <Tag color={statusColor(selectedRun.status)}>{statusText[selectedRun.status]}</Tag>}
        </div>
        {!history.length ? <Empty description="尚未运行实验；选择上方对象与任务后开始" /> : (
          <>
            <div className="history-toolbar">
              <Input
                allowClear
                prefix={<SearchOutlined />}
                value={historyQuery}
                onChange={(event) => setHistoryQuery(event.target.value)}
                placeholder="筛选实验对象、批次或任务"
                aria-label="筛选实验历史"
              />
              <span>{visibleHistory.length} / {history.length} 次运行</span>
            </div>
            <div className="process-layout">
              <div className="run-history">
                {!visibleHistory.length && <Empty description="没有匹配的历史运行" />}
                {visibleHistory.map((run) => (
                  <button
                    type="button"
                    key={run.batch_id}
                    className={run.batch_id === selectedBatchId ? "history-item active" : "history-item"}
                    onClick={() => { setSelectedBatchId(run.batch_id); setSelectedTaskId("") }}
                  >
                    <strong>{run.suite_name}</strong>
                    <code>{run.batch_id}</code>
                    <span>{run.completed_tasks}/{run.total_tasks} · {formatDateTime(run.started_at)}</span>
                  </button>
                ))}
              </div>
            {selectedRun && (
              <div className="run-detail">
                <div className="run-progress">
                  <Progress percent={progress} status={selectedRun.status === "failed" ? "exception" : running ? "active" : "success"} />
                  <div className="run-progress-copy">
                    <span>{selectedRun.current_task_id ? `正在执行：${selectedRun.current_task_id}` : `已完成 ${selectedRun.completed_tasks}/${selectedRun.total_tasks} 项`}</span>
                    <span>实验对象：{selectedRun.external_agent?.name || "项目内置参考宿主"}</span>
                    {selectedRun.model_id && <span>真实模型：{selectedRun.model_label ? `${selectedRun.model_label} · ` : ""}<code>{selectedRun.model_id}</code> · {reasoningModeLabel(selectedRun.model_reasoning_mode, selectedRun.model_id)}{selectedRun.model_sampling_params ? ` · 采样 ${JSON.stringify(selectedRun.model_sampling_params)}` : ""}（启动时已冻结）</span>}
                  </div>
                  {selectedRun.finished_at && (
                    <Button icon={<DownloadOutlined />} onClick={() => void saveSuiteReport(selectedRun.batch_id)}>下载套件 Markdown</Button>
                  )}
                </div>
                {selectedRun.error && <Alert type="warning" showIcon title={selectedRun.error} />}
                <div className="run-task-tabs" role="tablist" aria-label="套件任务">
                  {selectedRun.tasks.map((task) => (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selectedTask?.task_id === task.task_id}
                      className={selectedTask?.task_id === task.task_id ? "run-task active" : "run-task"}
                      key={task.task_id}
                      onClick={() => setSelectedTaskId(task.task_id)}
                    >
                      <span>{task.task_id}</span><Tag color={statusColor(task.status)}>{statusText[task.status]}</Tag>
                    </button>
                  ))}
                </div>
                {selectedTask && (
                  <TaskTrace
                    task={selectedTask}
                    advisorConfigured={advisorConfigured}
                    advisorModelId={advisorModelId}
                    adviceLoading={adviceLoading === `${selectedRun.batch_id}:${selectedTask.task_id}`}
                    onGenerateAdvice={generateAdvice}
                  />
                )}
              </div>
            )}
            </div>
          </>
        )}
      </section>
    </div>
  )
}

interface TaskTraceProps {
  task: SuiteTaskResult
  advisorConfigured: boolean
  advisorModelId: string | null
  adviceLoading: boolean
  onGenerateAdvice: () => Promise<void>
}

function frameworkPostcondition(task: SuiteTaskResult): Record<string, unknown> | null {
  const judgement = task.judgements.find((item) => item.layer === "framework")
  const evidence = judgement?.evidence
  return evidence && typeof evidence === "object" && !Array.isArray(evidence)
    ? evidence as Record<string, unknown>
    : null
}

function TaskTrace({ task, advisorConfigured, advisorModelId, adviceLoading, onGenerateAdvice }: TaskTraceProps) {
  const postcondition = frameworkPostcondition(task)
  const fileAbsent = postcondition?.kind === "file_absent"
  const hasFileEvidence = (postcondition?.kind === "file_written" || fileAbsent) && typeof postcondition.exists === "boolean"
  const postconditionPassed = hasFileEvidence && (
    fileAbsent
      ? postcondition.exists === false
      : postcondition.exists === true && postcondition.content_contains_ok !== false
  )
  const postconditionDescription = fileAbsent
    ? `沙箱文件 ${String(postcondition?.path)}：${postcondition?.exists ? "存在" : "不存在"}；本任务要求超时后不得写入。该检查直接核对实际文件状态，不依赖子进程是否返回结果。`
    : `沙箱文件 ${String(postcondition?.path)}：${postcondition?.exists ? "存在" : "不存在"}；内容匹配：${typeof postcondition?.content_contains_ok === "boolean" ? (postcondition.content_contains_ok ? "是" : "否") : "未要求"}。该检查由 Harness 在运行结束后直接执行，不依赖模型是否拥有读取工具。下方模型自述中的“未验证”只表示模型自身无法读回确认。`
  return (
    <div className="task-trace">
      <div className="trace-meta">
        <span><CheckCircleOutlined /> {task.host} · {task.mode}</span>
        <code>{task.run_id || "尚未生成 run_id"}</code>
      </div>
      {task.error && <Alert type="error" showIcon title="Harness 执行错误" description={task.error} />}
      {task.status === "running" && <div className="trace-waiting"><Spin size="small" /> 正在执行真实宿主；事件落盘后自动显示。</div>}
      {task.status === "pending" && <Empty description="等待前序任务完成" />}
      {!!task.judgements.length && (
        <div className="verdict-row">
          {task.judgements.map((judgement, index) => (
            <Tag key={index} color={judgement.verdict === "silent_failure" ? "error" : "blue"}>
              {String(judgement.layer)} / {String(judgement.verdict)}
            </Tag>
          ))}
        </div>
      )}
      {hasFileEvidence && (
        <Alert
          className="postcondition-alert"
          type={postconditionPassed ? "success" : "error"}
          showIcon
          title={`Harness 独立后置核验：${postconditionPassed ? "通过" : "未通过"}`}
          description={postconditionDescription}
        />
      )}
      {task.status === "completed" && (
        <section className="advice-panel">
          <div className="advice-heading">
            <div><BulbOutlined /><span><strong>LLM 修改建议</strong><small>依据预注册契约、实际轨迹与 Oracle；只供人工复核</small></span></div>
            <div className="advice-actions">
              <Tooltip title={advisorConfigured ? `使用 ${advisorModelId}；当前任务证据将发送到所选模型端点` : "请在本机 .env 配置带 chat 能力的模型；embedding-only 配置不会显示"}>
                <Button icon={<BulbOutlined />} loading={adviceLoading} disabled={!advisorConfigured} onClick={() => void onGenerateAdvice()}>
                  {task.advice ? "重新生成建议" : advisorConfigured ? "生成修改建议" : "缺少建议模型配置"}
                </Button>
              </Tooltip>
              {task.advice && <MarkdownDownloadButton content={task.advice} filename={`${task.run_id || task.task_id}-advice.md`} />}
            </div>
          </div>
          {task.advice ? (
            <div className="document-view compact advice-content" tabIndex={0} aria-label="LLM 修改建议，可滚动阅读">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{task.advice}</ReactMarkdown>
              <small className="advice-meta">由 {task.advice_model} 生成 · 未自动修改代码或实验判定</small>
            </div>
          ) : (
            <p className="advice-empty">完成实验后可生成针对性修改建议；建议不会自动应用，也不会改变上述判定。</p>
          )}
        </section>
      )}
      {!!task.events.length && (
        <>
          <div className="trace-evidence-heading"><strong>被测模型过程与自述</strong><small>只反映模型从工具消息和上下文中知道的事实，不替代上方的独立状态核验。</small></div>
          <ol className="event-timeline">
            {task.events.map((event, index) => (
              <li key={String(event.step_id || index)}>
                <div>
                  <strong>{eventTitle(event)}</strong>
                  <time dateTime={typeof event.timestamp === "string" ? event.timestamp : undefined}>{formatDateTime(typeof event.timestamp === "string" ? event.timestamp : null)}</time>
                </div>
                <pre>{eventText(event, task.events[index + 1])}</pre>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}
