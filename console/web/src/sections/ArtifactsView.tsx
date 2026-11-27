import { useEffect, useMemo, useState } from "react"
import { DownloadOutlined, FileTextOutlined } from "@ant-design/icons"
import { Alert, Button, Drawer, Empty, Spin, Tag } from "antd"
import ReactMarkdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import remarkGfm from "remark-gfm"
import { api } from "../api"
import type { Artifact, PublicReport } from "../types"
import { MarkdownDownloadButton } from "../components/MarkdownDownloadButton"
import { downloadMarkdown } from "../utils/downloadMarkdown"
import { formatDateTime } from "../utils/dateTime"

const modeLabels: Record<string, string> = {
  M0: "M0 · 预设脚本执行",
  M1: "M1 · 纯轨迹重放",
  M2: "M2 · 故障注入重放",
  M3: "M3 · 真实模型反事实续跑",
}

const hostLabels: Record<string, string> = {
  local_controlled: "本地受控宿主",
  smolagents: "smolagents 宿主",
  langgraph: "LangGraph 宿主",
}

const artifactFileLabels: Array<{ name: string; label: string }> = [
  { name: "run.json", label: "运行配置与预注册任务" },
  { name: "steps.jsonl", label: "逐步过程轨迹" },
  { name: "oracle.jsonl", label: "分层判定与证据" },
  { name: "report.md", label: "人读实验报告" },
]

function formatDate(value: string | null): string {
  return formatDateTime(value)
}

interface ReportState {
  id: string
  title: string
  context: string
  content: string
  filename: string
  kind: "run" | "public"
}

export function ArtifactsView({ artifacts }: { artifacts: Artifact[] }) {
  const [report, setReport] = useState<ReportState | null>(null)
  const [publicReports, setPublicReports] = useState<PublicReport[]>([])
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState("")
  const [error, setError] = useState("")
  const [taskMetadata, setTaskMetadata] = useState<Record<string, { description: string; expectedBehavior: string }>>({})

  useEffect(() => {
    let active = true
    // 兼容尚未重载新增字段的旧后端：一次读取套件目录，不逐份请求报告。
    api.experimentSuites().then((suites) => {
      if (!active) return
      const metadata: Record<string, { description: string; expectedBehavior: string }> = {}
      suites.forEach((suite) => suite.task_details.forEach((task) => {
        metadata[task.task_id] = { description: task.description, expectedBehavior: task.expected_behavior }
      }))
      setTaskMetadata(metadata)
    }).catch(() => null)
    api.publicReports().then((items) => {
      if (active) setPublicReports(items)
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : "公开报告读取失败")
    })
    return () => { active = false }
  }, [])

  const enrichedArtifacts = useMemo(() => artifacts.map((artifact) => {
    const metadata = artifact.task_id ? taskMetadata[artifact.task_id] : undefined
    return {
      ...artifact,
      description: artifact.description ?? metadata?.description ?? null,
      expected_behavior: artifact.expected_behavior ?? metadata?.expectedBehavior ?? null,
    }
  }), [artifacts, taskMetadata])

  async function openReport(artifact: Artifact) {
    const next: ReportState = {
      id: artifact.run_id,
      title: artifact.description || artifact.task_id || "实验运行报告",
      context: formatDate(artifact.created_at),
      content: "",
      filename: `${artifact.run_id}-report.md`,
      kind: "run",
    }
    setReport(next)
    setLoading(true)
    setError("")
    try {
      const content = await api.report(artifact.run_id)
      setReport((current) => current?.id === artifact.run_id ? { ...current, content } : current)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "报告读取失败")
    } finally {
      setLoading(false)
    }
  }

  async function openPublicReport(item: PublicReport) {
    setReport({
      id: item.path,
      title: item.title,
      context: `${item.date} · 公开验收报告`,
      content: "",
      filename: item.path.split("/").pop() || "public-report.md",
      kind: "public",
    })
    setLoading(true)
    setError("")
    try {
      const content = await api.publicReport(item.path)
      setReport((current) => current?.id === item.path ? { ...current, content } : current)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "公开报告读取失败")
    } finally {
      setLoading(false)
    }
  }

  async function saveReport(runId: string) {
    setDownloading(runId)
    setError("")
    try {
      const content = await api.report(runId)
      downloadMarkdown(`${runId}-report.md`, content)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "报告下载失败")
    } finally {
      setDownloading("")
    }
  }

  async function savePublicReport(item: PublicReport) {
    setDownloading(item.path)
    setError("")
    try {
      const content = await api.publicReport(item.path)
      downloadMarkdown(item.path.split("/").pop() || "public-report.md", content)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "公开报告下载失败")
    } finally {
      setDownloading("")
    }
  }

  return (
    <div className="view-stack">
      <div className="section-heading">
        <div><span className="section-kicker">RAW ARTIFACTS</span><h2>实验产物入口</h2></div>
        <span>{artifacts.length} 次运行</span>
      </div>
      <p className="status-explanation">每次运行保存配置、轨迹、判定和报告四个核心文件；文件齐全只说明产物完整，不代表被测 Agent 已通过测试。</p>
      {error && !report && <Alert type="error" showIcon title={error} />}
      {artifacts.length ? <div className="artifact-list">
        {enrichedArtifacts.map((artifact) => (
          <article className="artifact-row" key={`${artifact.path}-${artifact.run_id}`}>
            <div className="artifact-main">
              <span className="artifact-field-label">任务</span>
              <strong>{artifact.description || artifact.task_id || artifact.run_id}</strong>
              <code>任务 ID：{artifact.task_id || "未登记"}</code>
              <div className="artifact-goal"><span>任务目标</span><p>{artifact.expected_behavior || "该历史运行未记录可读的任务目标，请打开报告查看完整预注册信息。"}</p></div>
              <code>产物目录：{artifact.path}</code>
              {artifact.error && <Alert type="error" title={artifact.error} showIcon />}
            </div>
            <div className="artifact-facts">
              <div><span>执行宿主</span><strong>{artifact.host ? hostLabels[artifact.host] || artifact.host : "宿主未知"}</strong></div>
              <div><span>执行模式</span><strong>{artifact.mode ? modeLabels[artifact.mode] || artifact.mode : "模式未知"}</strong></div>
              <div><span>运行时间</span><strong>{formatDate(artifact.created_at)}</strong></div>
              <Tag color={artifact.complete ? "success" : "warning"}>{artifact.complete ? "四个核心文件齐全（4/4）" : `核心文件缺失（${artifact.files.length}/4）`}</Tag>
              <ul className="artifact-files" aria-label="四个核心产物文件">
                {artifactFileLabels.map((file) => {
                  const exists = artifact.files.includes(file.name)
                  return <li className={exists ? "is-present" : "is-missing"} key={file.name}><FileTextOutlined /><span><code>{file.name}</code> · {file.label}{exists ? "" : "（缺失）"}</span></li>
                })}
              </ul>
            </div>
            <div className="artifact-actions">
              <Button
                icon={<FileTextOutlined />}
                disabled={!artifact.files.includes("report.md")}
                onClick={() => void openReport(artifact)}
              >查看报告</Button>
              <Button
                icon={<DownloadOutlined />}
                loading={downloading === artifact.run_id}
                disabled={!artifact.files.includes("report.md")}
                onClick={() => void saveReport(artifact.run_id)}
              >下载 Markdown</Button>
            </div>
          </article>
        ))}
      </div> : <Empty description="尚未产生实验运行；先使用 faultlattice run 执行预注册任务" />}

      <div className="section-heading">
        <div><span className="section-kicker">PUBLIC ACCEPTANCE</span><h2>公开验收报告</h2></div>
        <span>{publicReports.length} 份已登记报告</span>
      </div>
      <p className="status-explanation">这里汇总可公开的实机验收、模型实验和复算报告；所有内容均可在线阅读或下载 Markdown。</p>
      {publicReports.length ? <section className="artifact-list public-reports" aria-label="公开验收报告">
        {publicReports.map((item) => (
          <article className="public-report-row" key={item.path}>
            <div className="public-report-copy">
              <strong>{item.title}</strong>
              <div className="public-report-meta"><span>{item.date}</span><span>{item.host}</span></div>
              <p>{item.summary}</p>
            </div>
            <div className="public-report-actions">
              <Button icon={<FileTextOutlined />} onClick={() => void openPublicReport(item)}>查看报告</Button>
              <Button icon={<DownloadOutlined />} loading={downloading === item.path} onClick={() => void savePublicReport(item)}>下载 Markdown</Button>
            </div>
          </article>
        ))}
      </section> : <Empty description="公开报告索引中尚无可用报告" />}
      <Drawer
        title={report ? `${report.title} · ${report.context}` : "实验报告"}
        size={820}
        open={report !== null}
        onClose={() => setReport(null)}
        destroyOnHidden
        extra={report?.content ? <MarkdownDownloadButton content={report.content} filename={report.filename} /> : undefined}
      >
        {report && <p className="report-drawer-meta">{report.kind === "run" ? "运行标识" : "公开报告"}：<code>{report.id}</code>。{report.kind === "run" ? "内容来自该次运行的原始产物" : "内容来自公开报告索引登记的文件"}，可复制或下载为 Markdown。</p>}
        {loading && <Spin />}
        {error && <Alert type="error" showIcon title={error} />}
        {!loading && !error && <div className="document-view compact"><ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{report?.content}</ReactMarkdown></div>}
      </Drawer>
    </div>
  )
}
