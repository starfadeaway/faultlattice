import { useCallback, useEffect, useRef, useState } from "react"
import {
  ApiOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  DeploymentUnitOutlined,
  FileAddOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons"
import { Alert, Button, Drawer, Empty, Input, Select, Spin, Tag, Tooltip } from "antd"
import { useNavigate } from "react-router"
import { api } from "../api"
import type { ExternalAgent, ModelOption } from "../types"
import { CodeViewer } from "../components/CodeViewer"
import { sourceDescription } from "../sourceDescriptions"
import { AdapterDraftAssistant } from "./external/AdapterDraftAssistant"
import { TaskAuthoring } from "./external/TaskAuthoring"

interface RegistrationForm {
  agent_id: string
  name: string
  entrypoint: string
  class_name: string
}

const emptyForm: RegistrationForm = {
  agent_id: "",
  name: "",
  entrypoint: "",
  class_name: "",
}

const referenceForm: RegistrationForm = {
  agent_id: "my-agent",
  name: "我的外部 Agent",
  entrypoint: "examples/external_agent/reference_agent.py",
  class_name: "ReferenceAgent",
}

const customForm: RegistrationForm = {
  agent_id: "my-custom-agent",
  name: "我的自定义 Agent",
  entrypoint: "external_agents/my_agent.py",
  class_name: "MyAgentAdapter",
}

const adapterPresets: Array<{
  id: string
  label: string
  purpose: string
  form: RegistrationForm
}> = [
  {
    id: "full",
    label: "完整参考循环 · 参数与结果故障",
    purpose: "用于验证一个独立 Python Agent 的完整 M0 接入：真实写入沙箱文件，支持 tool_args 与 tool_result 注入，并输出可被 Harness 复核的事件。",
    form: referenceForm,
  },
  {
    id: "args",
    label: "参数边界 · 仅 tool_args",
    purpose: "用于集中检查非法参数是否在工具执行前被拒绝。它不会登记 tool_result 能力，因此结果故障任务会在预检阶段被排除。",
    form: { ...referenceForm, agent_id: "my-args-agent", name: "我的参数边界 Agent", class_name: "ToolArgsReferenceAgent" },
  },
  {
    id: "result",
    label: "工具结果 · 仅 tool_result",
    purpose: "用于检查工具已经执行后，错误返回、异常或空结果如何传播。它不会登记 tool_args 能力，适合单独验收结果处理链。",
    form: { ...referenceForm, agent_id: "my-result-agent", name: "我的工具结果 Agent", class_name: "ToolResultReferenceAgent" },
  },
  {
    id: "custom",
    label: "自定义适配器 · 参考样式",
    purpose: "填写你自己的项目内 Python 文件与类名。下方代码样式给出最小可运行结构；生产接入应在自己的 run_script 中连接真实 Agent 循环。",
    form: customForm,
  },
]

const adapterReferenceSource = `from examples.external_agent.reference_agent import ReferenceAgent

class MyAgentAdapter(ReferenceAgent):
    name = "my_agent"
    package_version = "1.0.0"
    host_commit = None
    capabilities = {
        "modes": ["M0"],
        "injection_points": ["tool_args", "tool_result"],
        "tools": ["write_file"],
    }

    # 最小示例继承参考循环；生产适配器应重写 run_script，
    # 接入真实宿主，并如实返回 injection 与工具事件。`

const presetAgentIds = new Set(["reference-agent", "tool-args-agent", "tool-result-agent"])

type IntegrationSection = "register" | "tasks" | "hosts"

function requestedIntegrationSection(): IntegrationSection {
  const requested = new URLSearchParams(window.location.search).get("section")
  return requested === "tasks" || requested === "hosts" ? requested : "register"
}

export function ExternalAgentsView() {
  const [agents, setAgents] = useState<ExternalAgent[]>([])
  const [models, setModels] = useState<ModelOption[]>([])
  const [selectedTasks, setSelectedTasks] = useState<Record<string, string>>({})
  const [form, setForm] = useState<RegistrationForm>(referenceForm)
  const [presetId, setPresetId] = useState("full")
  const [activeSection, setActiveSection] = useState<IntegrationSection>(requestedIntegrationSection)
  const [source, setSource] = useState<{ path: string; content: string; className: string } | null>(null)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [sourceError, setSourceError] = useState("")
  const [modelOptionId, setModelOptionId] = useState("")
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const initialLoad = useRef(false)
  const navigate = useNavigate()
  const selectedPreset = adapterPresets.find((preset) => preset.id === presetId) || adapterPresets[0]
  const readyAgents = agents.filter((agent) => agent.status === "ready")
  const failedAgents = agents.filter((agent) => agent.status === "error")

  function applyPreset(id: string) {
    const preset = adapterPresets.find((item) => item.id === id)
    if (!preset) return
    setPresetId(id)
    setForm({ ...preset.form })
    setError("")
  }

  function useAdapterDraft(agentId: string, entrypoint: string, className: string) {
    setForm((current) => ({ ...current, agent_id: agentId, entrypoint, class_name: className }))
    setPresetId("custom")
    setActiveSection("register")
  }

  async function openSource(agent: ExternalAgent) {
    setSource({ path: agent.entrypoint, content: "", className: agent.class_name })
    setSourceLoading(true)
    setSourceError("")
    try {
      const content = await api.source(agent.entrypoint)
      setSource((current) => current?.className === agent.class_name ? { ...current, ...content } : current)
    } catch (reason) {
      setSourceError(reason instanceof Error ? reason.message : "适配器源码读取失败")
    } finally {
      setSourceLoading(false)
    }
  }

  const load = useCallback(async () => {
    setError("")
    try {
      const [agentData, modelData] = await Promise.all([
        api.externalAgents(),
        api.experimentModels().catch(() => []),
      ])
      setAgents(agentData)
      setModels(modelData)
      setSelectedTasks((current) => Object.fromEntries(agentData.map((agent) => [
        agent.id,
        agent.compatible_tasks.some((task) => task.path === current[agent.id])
          ? current[agent.id]
          : agent.compatible_tasks[0]?.path || "",
      ])))
      setModelOptionId((current) => {
        const preferred = current || window.localStorage.getItem("faultlattice.advisor-option") || ""
        return modelData.some((option) => option.id === preferred) ? preferred : modelData[0]?.id || ""
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "外部 Agent 登记读取失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (initialLoad.current) return
    initialLoad.current = true
    void load()
  }, [load])

  async function register() {
    setBusy("register")
    setError("")
    try {
      const registered = await api.registerExternalAgent({
        agent_id: form.agent_id.trim(),
        name: form.name.trim(),
        entrypoint: form.entrypoint.trim(),
        class_name: form.class_name.trim(),
      })
      setAgents((current) => [...current, registered])
      setSelectedTasks((current) => ({
        ...current,
        [registered.id]: registered.compatible_tasks[0]?.path || "",
      }))
      setForm(emptyForm)
      setPresetId("custom")
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "外部 Agent 登记失败")
    } finally {
      setBusy("")
    }
  }

  async function preflight(agentId: string) {
    setBusy(`preflight:${agentId}`)
    setError("")
    try {
      const inspected = await api.preflightExternalAgent(agentId)
      setAgents((current) => current.map((agent) => agent.id === agentId ? inspected : agent))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "外部 Agent 预检失败")
    } finally {
      setBusy("")
    }
  }

  async function run(agent: ExternalAgent) {
    const taskPath = selectedTasks[agent.id]
    if (!taskPath) return
    setBusy(`run:${agent.id}`)
    setError("")
    try {
      const task = agent.compatible_tasks.find((item) => item.path === taskPath)
      const run = await api.runExternalAgent(
        agent.id,
        taskPath,
        task?.mode === "M3" ? modelOptionId || undefined : undefined,
      )
      navigate(`/experiments?batch=${encodeURIComponent(run.batch_id)}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "外部 Agent 测试启动失败")
    } finally {
      setBusy("")
    }
  }

  if (loading) return <div className="initial-loading"><Spin size="large" description="正在加载并预检外部 Agent 适配器" /></div>

  return (
    <div className="view-stack external-agents-view">
      {error && <Alert type="error" showIcon title={error} />}
      <section className="experiment-intro external-intro">
        <div>
          <span className="section-kicker">EXTERNAL HOST ADAPTERS</span>
          <h2>接入你的 Agent，复用同一条可复算测试链</h2>
          <p>这里接入的是实现 HostAdapter 的 Agent 宿主，不是模型 API。登记后真实加载代码、核对能力与工具契约，再运行兼容的预注册任务。</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>重新加载与预检</Button>
      </section>

      <div className="monitor-tabs integration-tabs" role="tablist" aria-label="接入页面子视图">
        <div className="monitor-tabs-scroll">
          <button id="integration-register-tab" type="button" role="tab" aria-selected={activeSection === "register"} aria-controls="integration-register-panel" className={activeSection === "register" ? "monitor-tab active" : "monitor-tab"} onClick={() => setActiveSection("register")}><ApiOutlined />登记本地适配器</button>
          <button id="integration-tasks-tab" type="button" role="tab" aria-selected={activeSection === "tasks"} aria-controls="integration-tasks-panel" className={activeSection === "tasks" ? "monitor-tab active" : "monitor-tab"} onClick={() => setActiveSection("tasks")}><FileAddOutlined />任务创作</button>
          <button id="integration-hosts-tab" type="button" role="tab" aria-selected={activeSection === "hosts"} aria-controls="integration-hosts-panel" className={activeSection === "hosts" ? "monitor-tab active" : "monitor-tab"} onClick={() => setActiveSection("hosts")}><DeploymentUnitOutlined />已登记宿主（{readyAgents.length}）</button>
        </div>
      </div>

      <div id="integration-register-panel" className="integration-tab-panel" role="tabpanel" aria-labelledby="integration-register-tab" hidden={activeSection !== "register"}>
        <Alert
          type="warning"
          showIcon
          icon={<SafetyCertificateOutlined />}
          title="只登记你明确信任的本地 Python 代码"
          description="可直接选择上传适配器与说明文件，确认保存草案后再登记。登记和预检会执行模块顶层代码与构造函数；适配器必须如实记录 injection.original / replacement / applied，缺少有效注入证据会按 Harness 错误处理。"
        />
        <section className="settings-card external-register-card">
          <div className="settings-heading">
            <div><span className="section-kicker">REGISTER ADAPTER</span><h2>登记本地适配器</h2></div>
            <span>切换子页面不会清空输入</span>
          </div>
          <div className="adapter-preset-picker">
            <label>
              <span>适配器模板</span>
              <Select
                aria-label="适配器模板"
                value={presetId}
                options={adapterPresets.map((preset) => ({ value: preset.id, label: preset.label }))}
                onChange={applyPreset}
              />
            </label>
            <div className="adapter-preset-description">
              <strong>{selectedPreset.label}</strong>
              <p>{selectedPreset.purpose}</p>
              <code>{selectedPreset.form.entrypoint} · {selectedPreset.form.class_name}</code>
            </div>
          </div>
          <div className="adapter-form">
            <label><span>接入标识</span><Input value={form.agent_id} onChange={(event) => setForm({ ...form, agent_id: event.target.value })} placeholder="例如 my-agent" /></label>
            <label><span>显示名称</span><Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="例如 我的客服 Agent" /></label>
            <label><span>项目内 Python 文件</span><Input value={form.entrypoint} onChange={(event) => setForm({ ...form, entrypoint: event.target.value })} placeholder="external_agents/my_agent.py" /></label>
            <label><span>适配器类名</span><Input value={form.class_name} onChange={(event) => setForm({ ...form, class_name: event.target.value })} placeholder="MyAgentAdapter" /></label>
          </div>
          <details className="adapter-reference">
            <summary>查看自定义适配器参考样式</summary>
            <p>这是继承参考循环的最小可运行示例。接入生产 Agent 时，请在自己的文件中实现真实 run_script，不要只返回伪造事件。</p>
            <CodeViewer path="external_agents/my_agent.py" content={adapterReferenceSource} />
          </details>
          <div className="adapter-register-footer">
            <span>模板只填表，不自动登记。字段均可修改；类需可无参实例化，并声明 capabilities、preflight(fault) 与 run_script(...)。</span>
            <Button type="primary" icon={<ApiOutlined />} loading={busy === "register"} disabled={!Object.values(form).every((value) => value.trim())} onClick={() => void register()}>真实加载并登记</Button>
          </div>
        </section>
        <AdapterDraftAssistant currentAgentId={form.agent_id} models={models} modelOptionId={modelOptionId} onModelChange={setModelOptionId} onUseDraft={useAdapterDraft} />
      </div>

      <div id="integration-tasks-panel" className="integration-tab-panel" role="tabpanel" aria-labelledby="integration-tasks-tab" hidden={activeSection !== "tasks"}>
        <TaskAuthoring agents={agents} models={models} modelOptionId={modelOptionId} onModelChange={setModelOptionId} onChanged={load} />
      </div>

      <div id="integration-hosts-panel" className="integration-tab-panel" role="tabpanel" aria-labelledby="integration-hosts-tab" hidden={activeSection !== "hosts"}>
        <section className="external-registry">
          <div className="section-heading">
            <div><span className="section-kicker">REGISTERED HOSTS</span><h2>已登记宿主</h2></div>
            <span>{readyAgents.length} 个适配器 · 只陈列当前预检通过的宿主</span>
          </div>
          {failedAgents.length > 0 && <Alert type="warning" showIcon title={`${failedAgents.length} 个已登记项当前未通过预检，未纳入可运行列表`} description={failedAgents.map((agent) => `${agent.id}：${agent.error || "预检失败"}`).join("；")} />}
          {!readyAgents.length ? <Empty description="尚无预检通过的宿主；请先上传适配器并完成真实登记预检" /> : (
            <div className="external-agent-grid">
              {readyAgents.map((agent) => {
                const selectedPath = selectedTasks[agent.id] || ""
                const selectedTask = agent.compatible_tasks.find((task) => task.path === selectedPath) || null
                return (
                  <article className="suite-card external-agent-card" key={agent.id}>
                    <div className="external-agent-heading">
                      <span className="suite-icon"><DeploymentUnitOutlined /></span>
                      <div><strong>{agent.name}</strong><code>{agent.id} · {agent.class_name}</code></div>
                      <Tag color={agent.status === "ready" ? "success" : "error"}>{agent.status === "ready" ? "预检通过" : "预检失败"}</Tag>
                    </div>
                    <code className="adapter-entrypoint">{agent.entrypoint}</code>
                    {agent.error && <Alert type="error" showIcon title={agent.error} />}
                    {agent.capabilities && (
                      <div className="capability-tags">
                        <Tag color="blue">{agent.host_name} · v{agent.host_package_version || "未声明"}</Tag>
                        {agent.capabilities.modes.map((mode) => <Tag key={mode}>{mode}</Tag>)}
                        {agent.capabilities.injection_points.map((point) => <Tag color="purple" key={point}>{point}</Tag>)}
                        {agent.capabilities.tools.map((tool) => <Tag color="cyan" key={tool}>工具：{tool}</Tag>)}
                      </div>
                    )}
                    {agent.source_sha256 && <small className="source-hash">源码 SHA-256：<code>{agent.source_sha256}</code></small>}
                    <div className="external-task-picker">
                      <label>
                        <span>兼容的预注册任务（{agent.compatible_tasks.length}）</span>
                        <Select
                          value={selectedPath || undefined}
                          placeholder="没有兼容任务"
                          disabled={!agent.compatible_tasks.length}
                          options={agent.compatible_tasks.map((task) => ({
                            value: task.path,
                            label: `${task.origin === "custom" ? "自定义" : "内置"} · ${task.task_id} · ${task.mode}`,
                          }))}
                          onChange={(value) => setSelectedTasks((current) => ({ ...current, [agent.id]: value }))}
                        />
                      </label>
                      {selectedTask && (
                        <div className="external-task-detail">
                          <div className="task-kind-label"><Tag color={selectedTask.origin === "custom" ? "purple" : "blue"}>{selectedTask.origin === "builtin" ? "内置基础自检" : selectedTask.task_id.startsWith("pack-") ? "能力标准自检" : "自定义业务任务"}</Tag></div>
                          <strong>{selectedTask.description}</strong>
                          <p>目标：{selectedTask.expected_behavior}</p>
                          <small>评价层：{selectedTask.target_layers.join(" / ")}；故障：{selectedTask.fault ? `${String(selectedTask.fault.injection_point)} / ${String(selectedTask.fault.fault_type)} / ${String(selectedTask.fault.surface_as)}` : "无故障基线"}</small>
                          {selectedTask.mode === "M3" && (
                            <label>
                              <span>本次真实模型（启动时冻结）</span>
                              <Select
                                value={modelOptionId || undefined}
                                placeholder="缺少对话模型配置"
                                options={models.map((model) => ({ value: model.id, label: `${model.label} · ${model.model_id}` }))}
                                onChange={setModelOptionId}
                              />
                            </label>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="external-agent-actions">
                      {presetAgentIds.has(agent.id) && <Button icon={<CodeOutlined />} onClick={() => void openSource(agent)}>查看适配器代码</Button>}
                      <Tooltip title="重新读取当前源码并核对版本、能力和兼容任务">
                        <Button icon={<ReloadOutlined />} loading={busy === `preflight:${agent.id}`} onClick={() => void preflight(agent.id)}>重新预检</Button>
                      </Tooltip>
                      <Button
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        loading={busy === `run:${agent.id}`}
                        disabled={agent.status !== "ready" || !selectedTask || (selectedTask.mode === "M3" && !modelOptionId)}
                        onClick={() => void run(agent)}
                      >
                        运行并查看全过程
                      </Button>
                    </div>
                    <small className="external-run-note"><CheckCircleOutlined /> 启动后进入实验页查看事件与判定；结束后可生成 LLM 修改建议并下载 Markdown。</small>
                  </article>
                )
              })}
            </div>
          )}
        </section>
      </div>

      <Drawer
        title={source ? `${source.className} · ${sourceDescription(source.path)}` : "适配器源码"}
        size={900}
        open={source !== null}
        onClose={() => setSource(null)}
        destroyOnHidden
      >
        {source && <p className="report-drawer-meta">源码文件：<code>{source.path}</code>。三个预置适配器共用此文件，但声明不同的注入能力；当前抽屉对应 <strong>{source.className}</strong>。</p>}
        {sourceLoading && <Spin />}
        {sourceError && <Alert type="error" showIcon title={sourceError} />}
        {!sourceLoading && !sourceError && source && <CodeViewer path={source.path} content={source.content} />}
      </Drawer>
    </div>
  )
}
