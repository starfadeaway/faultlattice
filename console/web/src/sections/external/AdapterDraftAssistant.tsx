import { useState } from "react"
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CodeOutlined,
  DownloadOutlined,
  EyeOutlined,
  PythonOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  UploadOutlined,
} from "@ant-design/icons"
import { Alert, Button, Checkbox, Drawer, Empty, Input, Select, Spin, Tag, Upload } from "antd"
import { api } from "../../api"
import { CodeViewer } from "../../components/CodeViewer"
import type { AdapterDraftResult, ModelOption } from "../../types"
import { downloadText, readUtf8File } from "../../utils/files"

interface Props {
  currentAgentId: string
  models: ModelOption[]
  modelOptionId: string
  onModelChange: (id: string) => void
  onUseDraft: (agentId: string, entrypoint: string, className: string) => void
}

type QueueStatus = "running" | "completed" | "failed"

interface AdapterQueueItem {
  id: string
  agentId: string
  goal: string
  sourcePaths: string[]
  modelOptionId: string
  status: QueueStatus
  origin: "ai" | "upload"
  draft?: AdapterDraftResult
  content: string
  className: string
  error?: string
  savedPath?: string
  supplement: string
}

const defaultGoal = "根据项目 README 和参考实现，为一个真实文件写入 Agent 生成 HostAdapter 草案。声明实际支持的 M0、工具与故障注入点；信息不足处保留 TODO，不编造宿主接口。"
const acceptedDocuments = ".md,.txt,.py,.toml,.json,.yaml,.yml"

export function AdapterDraftAssistant({ currentAgentId, models, modelOptionId, onModelChange, onUseDraft }: Props) {
  const [sourcePaths, setSourcePaths] = useState("README.md\nexamples/external_agent/reference_agent.py")
  const [goal, setGoal] = useState(defaultGoal)
  const [queue, setQueue] = useState<AdapterQueueItem[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [riskConfirmed, setRiskConfirmed] = useState<Record<string, boolean>>({})
  const selected = queue.find((item) => item.id === selectedId) || null

  function paths(): string[] {
    return sourcePaths.split(/\r?\n/).map((path) => path.trim()).filter(Boolean)
  }

  function updateQueue(id: string, patch: Partial<AdapterQueueItem>) {
    setQueue((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  function openItem(id: string) {
    setSelectedId(id)
    setEditing(false)
  }

  function applyGoalTemplate(kind: "full" | "result" | "args") {
    if (kind === "full") setGoal(defaultGoal)
    if (kind === "result") setGoal("生成只支持 M0 与 tool_result 的文件写入 Agent 适配器草案。真实执行工具后再应用结果故障，完整记录注入前后内容；信息不足处保留 TODO。")
    if (kind === "args") setGoal("生成只支持 M0 与 tool_args 的文件写入 Agent 适配器草案。在工具执行前应用非法参数故障并核对拒绝行为；信息不足处保留 TODO。")
    setNotice("已替换目标模板；点击 AI 生成前仍可继续编辑。")
  }

  async function uploadReference(file: File) {
    setBusy("upload")
    setError("")
    try {
      if (paths().length >= 6) throw new Error("一次生成最多使用 6 个资料文件，请先移除不再需要的路径")
      const result = await api.uploadAdapterSource(file.name, await readUtf8File(file))
      setSourcePaths((current) => [...current.split(/\r?\n/).map((path) => path.trim()).filter(Boolean), result.path].join("\n"))
      setNotice(`${file.name} 已上传到本机资料区（${result.characters.toLocaleString()} 字符）；此操作尚未调用模型。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "资料文件上传失败")
    } finally {
      setBusy("")
    }
  }

  async function uploadAdapter(file: File) {
    setError("")
    setNotice("")
    try {
      const content = await readUtf8File(file, 60_000)
      const id = crypto.randomUUID()
      setQueue((current) => [{
        id,
        agentId: currentAgentId.trim(),
        goal: `本地上传适配器 ${file.name}；尚未执行、保存或登记。请核对说明、补充接入目标，并填写实际顶层适配器类名。`,
        sourcePaths: [],
        modelOptionId: "",
        status: "completed",
        origin: "upload",
        content,
        className: "",
        supplement: "",
      }, ...current])
      openItem(id)
      setNotice(`${file.name} 已读入草案队列；只有点击“确认保存草案”后才会写入项目。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Python 适配器读取失败")
    }
  }

  async function runGeneration(id: string, supplement = "") {
    const item = queue.find((entry) => entry.id === id)
    if (!item || !item.modelOptionId || !item.sourcePaths.length) return
    const combinedGoal = supplement.trim()
      ? `${item.goal}\n\n用户补充信息（仅作为本次改进约束）：\n${supplement.trim()}`
      : item.goal
    updateQueue(id, { status: "running", error: undefined, goal: combinedGoal })
    setBusy(`generate:${id}`)
    setError("")
    setNotice("")
    try {
      const result = await api.generateAdapterDraft(item.sourcePaths, combinedGoal, item.modelOptionId)
      updateQueue(id, {
        status: "completed",
        draft: result,
        content: result.content,
        className: result.class_name,
        supplement: "",
        savedPath: undefined,
      })
      setNotice(`${result.notice} 可在生成队列中查看说明和代码。`)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "AI 适配器草案生成失败"
      updateQueue(id, { status: "failed", error: message })
      setError(message)
    } finally {
      setBusy("")
    }
  }

  async function generate() {
    const sourceList = paths()
    if (!modelOptionId || goal.trim().length < 8 || !sourceList.length || !currentAgentId.trim()) return
    const id = crypto.randomUUID()
    const item: AdapterQueueItem = {
      id,
      agentId: currentAgentId.trim(),
      goal: goal.trim(),
      sourcePaths: sourceList,
      modelOptionId,
      status: "running",
      origin: "ai",
      content: "",
      className: "",
      supplement: "",
    }
    setQueue((current) => [item, ...current])
    setSelectedId(id)
    setEditing(false)
    // 直接以刚创建的条目执行，避免等待 React 状态提交后才启动队列任务。
    setBusy(`generate:${id}`)
    setError("")
    setNotice("")
    try {
      const result = await api.generateAdapterDraft(sourceList, goal.trim(), modelOptionId)
      updateQueue(id, { status: "completed", draft: result, content: result.content, className: result.class_name })
      setNotice(`${result.notice} 可在生成队列中查看说明和代码。`)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "AI 适配器草案生成失败"
      updateQueue(id, { status: "failed", error: message })
      setError(message)
    } finally {
      setBusy("")
    }
  }

  async function save(item: AdapterQueueItem) {
    if (!item.agentId.trim() || !item.className.trim() || !item.content.trim()) return
    if (item.savedPath) {
      onUseDraft(item.agentId, item.savedPath, item.className.trim())
      setSelectedId("")
      setNotice("已填入登记信息；请点击“真实加载并登记”，预检通过后才会进入已登记宿主。")
      return
    }
    setBusy(`save:${item.id}`)
    setError("")
    try {
      const result = await api.saveAdapterDraft(item.agentId.trim(), item.className.trim(), item.content, Boolean(riskConfirmed[item.id]))
      updateQueue(item.id, { savedPath: result.entrypoint })
      onUseDraft(item.agentId, result.entrypoint, result.class_name)
      setNotice(`${result.message} 登记与预检通过后才会进入“已登记宿主”。`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "适配器草案保存失败")
    } finally {
      setBusy("")
    }
  }

  return (
    <section className="settings-card authoring-card adapter-ai-card">
      <div className="settings-heading">
        <div><span className="section-kicker">ADAPTER INTAKE & GENERATION</span><h2>上传适配器或生成草案</h2></div>
        <Tag color="warning">确认后才保存</Tag>
      </div>
      <Alert
        type="warning"
        showIcon
        icon={<SafetyCertificateOutlined />}
        title="文件和 README 一律按不可信数据处理"
        description="文件选择后先进入本机工作区或草案队列，不会自动登记。生成代码只进入队列；你确认保存后，还要再次点击“真实加载并登记”，通过后才会进入已登记宿主。"
      />
      <div className="adapter-upload-grid">
        <div className="file-intake">
          <div><strong>上传已有 Python 适配器</strong><p>直接选择 .py 文件。先查看代码与填写类名，确认后才保存为 external_agents/drafts 中的草案。</p></div>
          <Upload accept=".py" showUploadList={false} beforeUpload={(file) => { void uploadAdapter(file); return false }}>
            <Button icon={<PythonOutlined />}>选择适配器 .py 文件</Button>
          </Upload>
        </div>
        <div className="file-intake">
          <div><strong>上传 Agent 说明与源码资料</strong><p>可一次选择多个 README、说明或源码文件；上传资料不等于调用 AI。单次生成最多使用 6 个文件。</p></div>
          <Upload accept={acceptedDocuments} multiple showUploadList={false} beforeUpload={(file) => { void uploadReference(file); return false }}>
            <Button icon={<UploadOutlined />} loading={busy === "upload"}>选择参考资料文件</Button>
          </Upload>
        </div>
      </div>
      <div className="adapter-ai-grid">
        <label><span>接入目标与约束</span><small>说明真实 Agent 的循环、工具、故障能力和已知限制；重新生成时还能继续补充。</small><Input.TextArea rows={5} value={goal} onChange={(event) => setGoal(event.target.value)} /></label>
        <div className="adapter-source-summary"><span>本次读取资料</span><small>默认使用项目 README 与参考实现；上传文件会自动加入，无需手写路径。</small><div className="draft-file-list">{paths().map((path) => <Tag key={path}>{path.split("/").pop()}</Tag>)}</div><details className="advanced-paths"><summary>高级：查看或编辑项目内资料路径</summary><Input.TextArea className="code-input" rows={4} value={sourcePaths} onChange={(event) => setSourcePaths(event.target.value)} /></details></div>
      </div>
      <div className="template-shortcuts" aria-label="适配器目标模板">
        <span>目标模板：</span>
        <Button size="small" onClick={() => applyGoalTemplate("full")}>完整参考循环</Button>
        <Button size="small" onClick={() => applyGoalTemplate("args")}>仅参数故障</Button>
        <Button size="small" onClick={() => applyGoalTemplate("result")}>仅结果故障</Button>
      </div>
      <div className="ai-generation-bar">
        <Select aria-label="适配器草案模型" value={modelOptionId || undefined} placeholder="未配置对话模型" options={models.map((model) => ({ value: model.id, label: `${model.label} · ${model.model_id}` }))} onChange={onModelChange} />
        <span>单文件 10,000 字符、总计 30,000 字符进入模型，超出会明确截断；上传原件仍保留在本机。</span>
        <Button icon={<RobotOutlined />} loading={busy.startsWith("generate:") && selectedId === queue[0]?.id} disabled={!modelOptionId || goal.trim().length < 8 || !sourcePaths.trim() || !currentAgentId.trim()} onClick={() => void generate()}>生成并加入适配器队列</Button>
      </div>
      {error && <Alert type="error" showIcon title={error} />}
      {notice && <Alert type="success" showIcon title={notice} />}

      <section className="adapter-generation-queue" aria-label="适配器生成队列">
        <div className="settings-heading"><div><span className="section-kicker">ADAPTER QUEUE</span><h3>适配器生成队列</h3></div><span>{queue.length} 项</span></div>
        {!queue.length ? <Empty description="尚无草案；可上传 Python 文件或选择资料后生成" /> : <div className="task-queue-list">{queue.map((item) => {
          const running = item.status === "running" || busy === `save:${item.id}`
          return <article className={`task-queue-row is-${item.status}`} key={item.id}>
            <div><strong>{item.agentId || "未命名适配器"}</strong><code>{item.origin === "upload" ? "本地 Python 上传" : item.draft?.model_id || item.modelOptionId}</code></div>
            <div><p>{item.goal}</p><small>{item.error || (item.savedPath ? `已保存：${item.savedPath}；等待登记预检` : item.className ? `识别类：${item.className} · 尚未登记` : "等待查看草案并填写适配器类名")}</small></div>
            <div className="task-queue-status">{running ? <Spin size="small" /> : item.status === "failed" ? <CloseCircleOutlined /> : item.savedPath ? <SaveOutlined /> : <CheckCircleOutlined />}<span>{running ? "处理中" : item.status === "failed" ? "失败" : item.savedPath ? "已保存" : "待确认"}</span><Button icon={<EyeOutlined />} onClick={() => openItem(item.id)}>查看</Button><Button icon={<RobotOutlined />} disabled={item.origin === "upload" || !item.modelOptionId} onClick={() => openItem(item.id)}>重来一次</Button></div>
          </article>
        })}</div>}
      </section>

      <Drawer title={selected ? `${selected.agentId || "适配器"} · 草案详情` : "适配器草案"} size={900} open={Boolean(selected)} onClose={() => { setSelectedId(""); setEditing(false) }}>
        {selected && <div className="adapter-draft-review">
          <div className="draft-review-heading"><Tag color={selected.savedPath ? "success" : selected.status === "failed" ? "error" : "warning"}>{selected.savedPath ? "已保存，待登记预检" : selected.status === "failed" ? "本次生成失败" : "尚未保存或登记"}</Tag><span>{selected.origin === "upload" ? "本地上传" : `模型：${selected.draft?.model_id || selected.modelOptionId}`}</span></div>
          {selected.error && <Alert type="error" showIcon title={selected.error} />}
          <section className="draft-explanation"><h3>适配器说明</h3><p>{selected.goal}</p><dl className="task-detail-list"><div><dt>当前适配器类</dt><dd>{selected.className || "尚未填写"}</dd></div><div><dt>资料与生成方式</dt><dd>{selected.origin === "upload" ? "来自用户明确选择的本地 Python 文件，未调用模型。" : selected.draft ? `实际读取 ${selected.draft.input_characters.toLocaleString()} 字符，估算输入约 ${selected.draft.estimated_input_tokens.toLocaleString()} Token（非账单）。` : "等待模型返回。"}</dd></div><div><dt>确认后的流程</dt><dd>保存草案 → 填入登记信息 → 用户点击真实加载并登记 → 预检通过后进入已登记宿主。</dd></div></dl></section>
          {selected.draft && selected.draft.files.length > 0 && <div className="draft-file-list">{selected.draft.files.map((file) => <Tag key={file.path} color={file.truncated ? "warning" : "default"}>{file.path.split("/").pop()} · {file.characters} 字符{file.truncated ? " · 已截断" : ""}</Tag>)}</div>}
          {selected.draft && selected.draft.warnings.length > 0 && <Alert type="warning" showIcon title="静态检查需要人工复核" description={<ul>{selected.draft.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>} />}
          {selected.content && <>
            <label className="draft-class-field"><span>顶层适配器类名</span><small>保存和真实加载时使用；上传已有文件时必须与代码中的类名一致。</small><Input value={selected.className} onChange={(event) => updateQueue(selected.id, { className: event.target.value, savedPath: undefined })} placeholder="例如 MyAgentAdapter" /></label>
            <div className="draft-code-heading"><div><strong>Python 草案</strong><small>默认只读高亮代码块；需要修改时再切换编辑。</small></div><Button icon={<CodeOutlined />} onClick={() => setEditing((value) => !value)}>{editing ? "返回高亮预览" : "编辑代码"}</Button></div>
            {editing ? <Input.TextArea className="code-input adapter-draft-code" value={selected.content} onChange={(event) => updateQueue(selected.id, { content: event.target.value, savedPath: undefined })} rows={20} /> : <CodeViewer path={`${selected.agentId || "agent-adapter"}.py`} content={selected.content} />}
          </>}
          {selected.content && !selected.savedPath && <Checkbox checked={Boolean(riskConfirmed[selected.id])} onChange={(event) => setRiskConfirmed((current) => ({ ...current, [selected.id]: event.target.checked }))}>我已人工检查动态导入、Agent.run、文件删除等调用；普通复核警告允许保存，硬阻断调用仍会被后端拒绝。</Checkbox>}
          {selected.origin === "ai" && <div className="regenerate-panel"><label><span>补充信息后重新生成</span><small>可补充真实宿主 API、事件格式、缺失能力或上一次的问题；留空则按原目标重试。旧草案只有在新草案成功后才替换。</small><Input.TextArea rows={4} value={selected.supplement} onChange={(event) => updateQueue(selected.id, { supplement: event.target.value })} placeholder="例如：实际宿主使用 async run()，工具返回必须包含 call_id；请不要继承参考循环。" /></label><Button icon={<RobotOutlined />} loading={busy === `generate:${selected.id}`} disabled={!selected.modelOptionId} onClick={() => void runGeneration(selected.id, selected.supplement)}>确认并重新生成</Button></div>}
          <div className="draft-actions"><span>{selected.savedPath ? `已保存到 ${selected.savedPath}，仍需登记预检。` : `保存目标：external_agents/drafts/${selected.agentId || "未填写接入标识"}.py；已有文件不会覆盖。`}</span><Button icon={<DownloadOutlined />} disabled={!selected.content} onClick={() => downloadText(`${selected.agentId || "agent-adapter"}.py`, selected.content, "text/x-python;charset=utf-8")}>下载 Python</Button><Button type="primary" icon={<SaveOutlined />} loading={busy === `save:${selected.id}`} disabled={!selected.content.trim() || !selected.className.trim() || !selected.agentId.trim()} onClick={() => void save(selected)}>{selected.savedPath ? "再次填入登记信息" : "确认保存草案"}</Button></div>
        </div>}
      </Drawer>
    </section>
  )
}
