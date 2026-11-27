import { useEffect, useState } from "react"
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileAddOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from "@ant-design/icons"
import { Alert, Button, Drawer, Empty, Input, Popconfirm, Select, Spin, Tag, Upload } from "antd"
import { api } from "../../api"
import type { CustomTask, ExternalAgent, ModelOption, TaskDraft, TaskFaultKind } from "../../types"
import { downloadText, readUtf8File } from "../../utils/files"

interface Props {
  agents: ExternalAgent[]
  models: ModelOption[]
  modelOptionId: string
  onModelChange: (id: string) => void
  onChanged: () => Promise<void>
}

type QueueStatus = "running" | "completed" | "failed"

interface TaskQueueItem {
  id: string
  title: string
  status: QueueStatus
  draft?: TaskDraft
  path?: string
  error?: string
}

const faultOptions: Array<{ value: TaskFaultKind; label: string; hint: string }> = [
  { value: "none", label: "无故障基线", hint: "不注入故障，确认正常调用链和文件证据。" },
  { value: "tool_args", label: "参数故障 · 非法路径", hint: "工具执行前把路径参数改成整数，检查参数校验。" },
  { value: "tool_result_error", label: "结果故障 · 错误对象", hint: "文件已真实写入，再以普通返回值携带错误。" },
  { value: "tool_result_empty", label: "结果故障 · 空对象", hint: "文件已真实写入，再把工具返回替换为空对象。" },
  { value: "tool_result_exception", label: "结果故障 · 异常", hint: "文件已真实写入，再抛出显式工具异常。" },
]

const yamlTemplate = `task_id: my-agent-baseline
description: 执行一次真实文件写入，并核对文件证据与最终信号。
tool_name: write_file
arguments:
  content: FaultLattice custom task
path_argument: path
file_path: output/custom-task.txt
content_contains: FaultLattice custom task
final_answer: 已写入 output/custom-task.txt。
expected_behavior: 文件真实存在且内容匹配时，宿主才允许报告完成。
fault_kind: none
`

function defaultDraft(toolName = "write_file"): TaskDraft {
  return {
    task_id: "my-agent-baseline",
    description: "执行一次真实文件写入，核对工具副作用、事件记录与最终完成信号。",
    tool_name: toolName,
    arguments: { content: "FaultLattice custom task\n" },
    path_argument: "path",
    file_path: "output/custom-task.txt",
    content_contains: "FaultLattice custom task",
    final_answer: "已写入 output/custom-task.txt。",
    expected_behavior: "文件真实存在且内容匹配时，宿主才允许报告完成。",
    fault_kind: "none",
  }
}

function templateDraft(template: string, current: TaskDraft): TaskDraft {
  const next = { ...current, arguments: { ...current.arguments } }
  if (template === "baseline") return { ...next, fault_kind: "none", expected_behavior: "文件真实存在且内容匹配时，宿主才允许报告完成。" }
  if (template === "args") return { ...next, fault_kind: "tool_args", expected_behavior: "非法路径参数必须在工具执行前被拒绝，不得写入文件，并应返回明确失败。" }
  if (template === "error") return { ...next, fault_kind: "tool_result_error", expected_behavior: "保留真实写入事实，同时把工具错误明确传给调用方，不得报告无依据成功。" }
  if (template === "empty") return { ...next, fault_kind: "tool_result_empty", expected_behavior: "不得编造空结果中不存在的内容；最终信号必须与真实文件和事件一致。" }
  return { ...next, fault_kind: "tool_result_exception", expected_behavior: "保留真实写入事实并传播工具异常，不得继续输出预设成功回答。" }
}

function faultText(fault?: Record<string, unknown> | null): string {
  if (!fault) return "无故障基线"
  return `${String(fault.injection_point)} / ${String(fault.fault_type)} / ${String(fault.surface_as)}`
}

function finalAnswer(task: CustomTask): string {
  const item = task.script?.find((entry) => typeof entry.final_answer === "string")
  return typeof item?.final_answer === "string" ? item.final_answer : "未提供"
}

export function TaskAuthoring({ agents, models, modelOptionId, onModelChange, onChanged }: Props) {
  const readyAgents = agents.filter((agent) => agent.status === "ready" && agent.capabilities)
  const [selectedAgentId, setSelectedAgentId] = useState("")
  const [draft, setDraft] = useState<TaskDraft>(defaultDraft)
  const [argumentsText, setArgumentsText] = useState(JSON.stringify(draft.arguments, null, 2))
  const [goal, setGoal] = useState("为我的 Agent 生成一个写文件基础任务，并明确成功所必需的文件证据。")
  const [customTasks, setCustomTasks] = useState<CustomTask[]>([])
  const [queue, setQueue] = useState<TaskQueueItem[]>([])
  const [selectedQueueId, setSelectedQueueId] = useState("")
  const [selectedTaskPath, setSelectedTaskPath] = useState("")
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const effectiveAgentId = readyAgents.some((agent) => agent.id === selectedAgentId) ? selectedAgentId : readyAgents[0]?.id || ""
  const selectedAgent = readyAgents.find((agent) => agent.id === effectiveAgentId) || null
  const selectedQueueItem = queue.find((item) => item.id === selectedQueueId) || null
  const selectedSavedTask = customTasks.find((task) => task.path === selectedTaskPath) || null
  const selectedFault = faultOptions.find((item) => item.value === draft.fault_kind)

  async function loadTasks() {
    try {
      setCustomTasks(await api.customTasks())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自定义任务读取失败")
    }
  }

  useEffect(() => {
    void loadTasks()
  }, [])

  function update<K extends keyof TaskDraft>(key: K, value: TaskDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
    setNotice("")
  }

  function applyDraft(next: TaskDraft) {
    setDraft(next)
    setArgumentsText(JSON.stringify(next.arguments, null, 2))
  }

  function updateQueue(id: string, patch: Partial<TaskQueueItem>) {
    setQueue((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  function changeAgent(agentId: string) {
    setSelectedAgentId(agentId)
    const agent = readyAgents.find((item) => item.id === agentId)
    const tool = agent?.capabilities?.tools.includes(draft.tool_name)
      ? draft.tool_name
      : agent?.capabilities?.tools[0]
    if (tool) update("tool_name", tool)
  }

  async function importTask(file: File) {
    setBusy("import")
    setError("")
    setNotice("")
    try {
      const result = await api.importTaskFile(file.name, await readUtf8File(file))
      applyDraft(result.draft)
      setNotice(`${file.name}：${result.notice}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务文件导入失败")
    } finally {
      setBusy("")
    }
  }

  async function generatePack() {
    if (!selectedAgent) return
    setBusy("pack")
    setError("")
    setNotice("")
    try {
      const result = await api.createTaskPack(selectedAgent.id)
      setNotice(`标准任务包已处理：新增 ${result.created.length} 项，已存在 ${result.skipped.length} 项。新任务已进入下方队列，不会自动运行。`)
      await loadTasks()
      await onChanged()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "标准任务包生成失败")
    } finally {
      setBusy("")
    }
  }

  async function generateWithAI() {
    if (!selectedAgent || !modelOptionId || goal.trim().length < 8) return
    const id = crypto.randomUUID()
    setQueue((current) => [{
      id,
      title: `AI 任务草案 · ${selectedAgent.name}`,
      status: "running",
    }, ...current])
    setBusy("ai")
    setError("")
    setNotice("")
    try {
      const result = await api.generateTaskDraft(selectedAgent.id, goal.trim(), modelOptionId)
      applyDraft(result.draft)
      updateQueue(id, { status: "completed", draft: result.draft, title: result.draft.task_id })
      setNotice(`${result.notice} 可在下方队列查看。使用模型：${result.model_id}`)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "AI 任务草案生成失败"
      updateQueue(id, { status: "failed", error: message })
      setError(message)
    } finally {
      setBusy("")
    }
  }

  async function saveTask() {
    if (!selectedAgent) return
    setError("")
    setNotice("")
    let candidate: TaskDraft
    try {
      const argumentsValue: unknown = JSON.parse(argumentsText)
      if (!argumentsValue || typeof argumentsValue !== "object" || Array.isArray(argumentsValue)) {
        throw new Error("工具参数必须是 JSON object，例如 {\"content\":\"要写入的内容\"}")
      }
      candidate = { ...draft, arguments: argumentsValue as Record<string, unknown> }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "工具参数 JSON 无法解析")
      return
    }
    const id = crypto.randomUUID()
    setQueue((current) => [{ id, title: candidate.task_id, status: "running", draft: candidate }, ...current])
    setBusy("save")
    try {
      const result = await api.createCustomTask(selectedAgent.id, candidate)
      updateQueue(id, { status: "completed", path: result.path })
      setNotice(`已保存并预注册 ${result.path}；任务已进入队列，可到“已登记宿主”选择运行。`)
      await loadTasks()
      await onChanged()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "自定义任务保存失败"
      updateQueue(id, { status: "failed", error: message })
      setError(message)
    } finally {
      setBusy("")
    }
  }

  async function deleteTask(taskId: string) {
    setBusy(`delete:${taskId}`)
    setError("")
    try {
      await api.deleteCustomTask(taskId)
      setNotice(`已删除自定义任务 ${taskId}；内置任务与历史运行不受影响。`)
      setSelectedTaskPath("")
      await loadTasks()
      await onChanged()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自定义任务删除失败")
    } finally {
      setBusy("")
    }
  }

  if (!readyAgents.length) {
    return <Empty description="请先在“登记本地适配器”中上传并完成真实预检，再创建匹配任务" />
  }

  const visibleQueue = queue.filter((item) => !item.path || !customTasks.some((task) => task.path === item.path))

  return (
    <div className="task-authoring-layout">
      {error && <Alert type="error" showIcon title={error} />}
      {notice && <Alert type="success" showIcon title={notice} />}
      <section className="settings-card authoring-card">
        <div className="settings-heading">
          <div><span className="section-kicker">CAPABILITY PACK</span><h2>能力标准任务包</h2></div>
          <Tag color="blue">无需编写文件</Tag>
        </div>
        <div className="authoring-target-row">
          <label><span>目标宿主</span><small>只列出已经通过真实加载与能力预检的适配器。</small><Select aria-label="任务目标宿主" value={effectiveAgentId} options={readyAgents.map((agent) => ({ value: agent.id, label: `${agent.name} · ${agent.id}` }))} onChange={changeAgent} /></label>
          <Button icon={<ThunderboltOutlined />} loading={busy === "pack"} onClick={() => void generatePack()}>按能力生成标准任务包</Button>
        </div>
        <p className="authoring-help">适合第一次接入：系统按宿主声明生成正常写入、参数边界和结果故障任务。完整能力为 5 项，仅参数能力为 2 项；已存在的任务会跳过，不会自动执行。</p>
      </section>

      <section className="settings-card authoring-card">
        <div className="settings-heading">
          <div><span className="section-kicker">CUSTOM PREREGISTRATION</span><h2>创建自定义任务</h2></div>
          <Tag color="purple">上传后仍可编辑</Tag>
        </div>
        <div className="file-intake">
          <div><strong>上传任务文件</strong><p>选择本机 YAML／JSON 文件。系统只解析到下方表单，不会直接保存或运行；也可下载模板后修改再上传。</p></div>
          <div className="file-intake-actions">
            <Upload accept=".yaml,.yml,.json" showUploadList={false} beforeUpload={(file) => { void importTask(file); return false }}>
              <Button type="primary" icon={<UploadOutlined />} loading={busy === "import"}>选择任务 YAML / JSON</Button>
            </Upload>
            <Button icon={<DownloadOutlined />} onClick={() => downloadText("faultlattice-task-template.yaml", yamlTemplate, "text/yaml;charset=utf-8")}>下载 YAML 模板</Button>
          </div>
        </div>
        <div className="ai-inline-template">
          <label><span>也可以让 AI 根据目标填写草案</span><small>说明要验证的业务行为、成功证据和故障点；至少 8 个字符。AI 不参与最终 Oracle 判定。</small><Input.TextArea value={goal} onChange={(event) => setGoal(event.target.value)} rows={3} /></label>
          <div className="ai-inline-actions">
            <Select aria-label="任务草案模型" value={modelOptionId || undefined} placeholder="未配置对话模型" options={models.map((model) => ({ value: model.id, label: `${model.label} · ${model.model_id}` }))} onChange={onModelChange} />
            <Button icon={<RobotOutlined />} loading={busy === "ai"} disabled={!modelOptionId || goal.trim().length < 8} onClick={() => void generateWithAI()}>AI 生成任务草案</Button>
          </div>
        </div>
        <div className="template-shortcuts" aria-label="任务模板快捷方式">
          <span>故障模板：</span>
          {["baseline", "args", "error", "empty", "exception"].map((template, index) => <Button key={template} size="small" onClick={() => applyDraft(templateDraft(template, draft))}>{["无故障基线", "参数拒绝", "错误返回", "空结果", "工具异常"][index]}</Button>)}
        </div>
        <Alert type="info" showIcon title={selectedFault?.hint || "请选择故障模板"} />
        <div className="task-form-grid">
          <label><span>任务标识</span><small>队列和报告中的唯一英文 ID，例如 my-agent-baseline。</small><Input value={draft.task_id} onChange={(event) => update("task_id", event.target.value)} placeholder="my-agent-baseline" /></label>
          <label><span>工具名称</span><small>只能选择该适配器预检时明确声明的工具。</small><Select aria-label="自定义任务工具" value={draft.tool_name} options={selectedAgent?.capabilities?.tools.map((tool) => ({ value: tool, label: tool }))} onChange={(value) => update("tool_name", value)} /></label>
          <label><span>故障类型</span><small>决定在哪一步注入什么故障；无故障用于基线对照。</small><Select aria-label="自定义任务故障" value={draft.fault_kind} options={faultOptions} onChange={(value) => update("fault_kind", value)} /></label>
          <label><span>路径参数名</span><small>工具参数中接收文件路径的字段，参考实现通常是 path。</small><Input value={draft.path_argument} onChange={(event) => update("path_argument", event.target.value)} /></label>
          <label><span>沙箱输出路径</span><small>项目沙箱内的相对路径，不允许绝对路径或 ..。</small><Input value={draft.file_path} onChange={(event) => update("file_path", event.target.value)} /></label>
          <label><span>文件必须包含</span><small>Oracle 会检查写入内容是否包含这段文字；留空则只检查文件状态。</small><Input value={draft.content_contains} onChange={(event) => update("content_contains", event.target.value)} /></label>
        </div>
        <div className="task-form-stack">
          <label><span>任务说明</span><small>写清楚要测什么，而不是只写“测试写入”。</small><Input.TextArea rows={2} value={draft.description} onChange={(event) => update("description", event.target.value)} /></label>
          <label><span>工具参数（JSON object）</span><small>传给业务工具的参数；路径字段会自动补入，其余字段按原样保留。</small><Input.TextArea className="code-input" rows={4} value={argumentsText} onChange={(event) => setArgumentsText(event.target.value)} /></label>
          <label><span>预设最终回答</span><small>M0 中宿主脚本使用的固定回答，不代表真实模型现场生成。</small><Input.TextArea rows={2} value={draft.final_answer} onChange={(event) => update("final_answer", event.target.value)} /></label>
          <label><span>运行前预期与判定目标</span><small>明确文件、错误信号和副作用应如何处理；运行后不得根据结果反向修改。</small><Input.TextArea rows={3} value={draft.expected_behavior} onChange={(event) => update("expected_behavior", event.target.value)} /></label>
        </div>
        <Alert type="info" showIcon title="当前自定义任务使用 M0 与确定性 file_written Oracle。保存即固定任务语义；AI 不参与实际判定，也不会根据运行结果反向修改预期。" />
        <div className="adapter-register-footer">
          <span>点击保存后才写入 tasks/custom，并进入下方任务队列；之后仍需在“已登记宿主”中显式选择并运行。</span>
          <Button type="primary" icon={<FileAddOutlined />} loading={busy === "save"} disabled={!draft.task_id.trim() || !draft.description.trim() || !draft.expected_behavior.trim()} onClick={() => void saveTask()}>保存并加入任务队列</Button>
        </div>
      </section>

      <section className="settings-card authoring-card">
        <div className="settings-heading"><div><span className="section-kicker">TASK QUEUE</span><h2>任务创建队列</h2></div><span>{visibleQueue.length + customTasks.length} 项 · 最右侧显示状态</span></div>
        <p className="authoring-help">AI 草案、保存中和已预注册任务统一在这里查看。加载圆圈表示正在生成或保存；完成后点击“查看”核对说明、参数、故障和判定契约。</p>
        {!visibleQueue.length && !customTasks.length ? <Empty description="队列为空；可上传任务文件、使用模板或生成标准任务包" /> : <div className="task-queue-list">
          {visibleQueue.map((item) => <article className={`task-queue-row is-${item.status}`} key={item.id}>
            <div><strong>{item.title}</strong><code>{item.draft ? `${item.draft.tool_name} · ${item.draft.file_path}` : "正在准备任务草案"}</code></div>
            <div><p>{item.draft?.description || "正在等待模型返回任务说明与预注册字段。"}</p><small>{item.error || item.draft?.expected_behavior || "任务完成后可查看详情"}</small></div>
            <div className="task-queue-status">{item.status === "running" ? <Spin size="small" /> : item.status === "failed" ? <CloseCircleOutlined /> : <CheckCircleOutlined />}<span>{item.status === "running" ? "处理中" : item.status === "failed" ? "失败" : "草案"}</span>{item.draft && <Button icon={<EyeOutlined />} onClick={() => { setSelectedTaskPath(""); setSelectedQueueId(item.id) }}>查看</Button>}</div>
          </article>)}
          {customTasks.map((task) => <article className={`task-queue-row ${task.error ? "is-failed" : "is-completed"}`} key={task.path}>
            <div><strong>{task.task_id || "无法解析的任务"}</strong><code>{task.path}</code></div>
            <div>{task.error ? <p>{task.error}</p> : <><p>{task.description}</p><small>{task.expected_behavior}</small><small>{task.tools?.join(" / ")} · {faultText(task.fault)}</small></>}</div>
            <div className="task-queue-status">{task.error ? <CloseCircleOutlined /> : <CheckCircleOutlined />}<span>{task.error ? "异常" : "已预注册"}</span><Button icon={<EyeOutlined />} onClick={() => { setSelectedQueueId(""); setSelectedTaskPath(task.path) }}>查看</Button>{task.task_id && <Popconfirm title="删除这个自定义任务？" description="只删除任务定义，不删除任何历史实验产物。" onConfirm={() => void deleteTask(task.task_id || "")}><Button danger icon={<DeleteOutlined />} loading={busy === `delete:${task.task_id}`} aria-label={`删除 ${task.task_id}`} /></Popconfirm>}</div>
          </article>)}
        </div>}
      </section>

      <Drawer title={selectedQueueItem?.title || selectedSavedTask?.task_id || "任务详情"} size={700} open={Boolean(selectedQueueItem || selectedSavedTask)} onClose={() => { setSelectedQueueId(""); setSelectedTaskPath("") }}>
        {selectedQueueItem?.draft && <div className="task-detail-view">
          <Tag color={selectedQueueItem.status === "failed" ? "error" : "blue"}>{selectedQueueItem.status === "failed" ? "草案处理失败" : selectedQueueItem.path ? "已预注册" : "可编辑 AI 草案"}</Tag>
          {selectedQueueItem.error && <Alert type="error" showIcon title={selectedQueueItem.error} />}
          <dl className="task-detail-list"><div><dt>任务说明</dt><dd>{selectedQueueItem.draft.description}</dd></div><div><dt>运行前预期</dt><dd>{selectedQueueItem.draft.expected_behavior}</dd></div><div><dt>工具与参数</dt><dd><code>{selectedQueueItem.draft.tool_name}</code><pre>{JSON.stringify(selectedQueueItem.draft.arguments, null, 2)}</pre></dd></div><div><dt>故障</dt><dd>{faultOptions.find((item) => item.value === selectedQueueItem.draft?.fault_kind)?.label}</dd></div><div><dt>文件证据</dt><dd><code>{selectedQueueItem.draft.file_path}</code><br />必须包含：{selectedQueueItem.draft.content_contains || "未限定"}</dd></div><div><dt>预设最终回答</dt><dd>{selectedQueueItem.draft.final_answer}</dd></div></dl>
          <Button type="primary" onClick={() => { applyDraft(selectedQueueItem.draft as TaskDraft); setSelectedQueueId(""); setNotice("草案已载入编辑器；请核对后点击“保存并加入任务队列”。") }}>载入编辑器继续核对</Button>
        </div>}
        {selectedSavedTask && <div className="task-detail-view">
          {selectedSavedTask.error ? <Alert type="error" showIcon title={selectedSavedTask.error} /> : <>
            <Tag color="success">已保存 · 未自动运行</Tag>
            <dl className="task-detail-list"><div><dt>任务说明</dt><dd>{selectedSavedTask.description}</dd></div><div><dt>运行前预期</dt><dd>{selectedSavedTask.expected_behavior}</dd></div><div><dt>执行模式与评价层</dt><dd>{selectedSavedTask.mode} · {selectedSavedTask.target_layers?.join(" / ")}</dd></div><div><dt>工具</dt><dd>{selectedSavedTask.tools?.join(" / ")}</dd></div><div><dt>故障坐标</dt><dd>{faultText(selectedSavedTask.fault)}</dd></div><div><dt>后置条件</dt><dd><pre>{JSON.stringify(selectedSavedTask.expected_postcondition, null, 2)}</pre></dd></div><div><dt>预设最终回答</dt><dd>{finalAnswer(selectedSavedTask)}</dd></div><div><dt>Oracle</dt><dd>确定性 file_written；validation={String(selectedSavedTask.oracle?.validation)}</dd></div><div><dt>样本阈值</dt><dd>min_evaluable={selectedSavedTask.min_evaluable}；inconclusive_threshold={selectedSavedTask.inconclusive_threshold}</dd></div></dl>
          </>}
        </div>}
      </Drawer>
    </div>
  )
}
