import { useState } from "react"
import { CodeOutlined } from "@ant-design/icons"
import { Alert, Button, Drawer, Empty, Spin } from "antd"
import { api } from "../api"
import type { ProjectModule } from "../types"
import { sourceDescription } from "../sourceDescriptions"
import { StatusTag } from "../components/StatusTag"
import { CodeViewer } from "../components/CodeViewer"
import { DependencyTag } from "../components/DependencyTag"
import { toneFor } from "../utils/dependencyTone"
import { MarkdownDownloadButton } from "../components/MarkdownDownloadButton"

interface Props {
  modules: ProjectModule[]
  selectedId: string
  onSelect: (id: string) => void
}

export function ModulesView({ modules, selectedId, onSelect }: Props) {
  const selected = modules.find((module) => module.id === selectedId) || modules[0]
  const [source, setSource] = useState<{ path: string; content: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function openSource(path: string) {
    setLoading(true)
    setError("")
    setSource({ path, content: "" })
    try {
      setSource(await api.source(path))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "源码读取失败")
    } finally {
      setLoading(false)
    }
  }

  if (!selected) return <Empty description="项目清单中没有模块" />
  return (
    <div className="module-workspace">
      <aside className="module-list" aria-label="模块列表">
        {modules.map((module) => (
          <button
            type="button"
            key={module.id}
            className={`module-list-item module-tone-${toneFor(module.id)}${module.id === selected.id ? " active" : ""}`}
            onClick={() => onSelect(module.id)}
          >
            <span><strong>{module.name}</strong><code>{module.id}</code></span>
            <StatusTag status={module.status} />
          </button>
        ))}
      </aside>
      <section className="module-detail" key={selected.id}>
        <div className="section-heading">
          <div><span className="section-kicker">MODULE / {selected.id}</span><h2>{selected.name}</h2></div>
          <StatusTag status={selected.status} />
        </div>
        <p className="status-explanation">
          状态由路径存在性与全部指定验收实时推导；清单不包含人工 status。
        </p>
        <div className="detail-grid">
          <div>
            <h3>代码入口</h3>
            <div className="file-list">
              {selected.source_files.map((path) => (
                <Button key={path} type="text" icon={<CodeOutlined />} onClick={() => openSource(path)}>
                  <span className="file-entry"><code>{path}</code><small>{sourceDescription(path)}</small></span>
                </Button>
              ))}
            </div>
          </div>
          <div>
            <h3>测试路径</h3>
            {selected.test_paths.map((path) => <div className="path-row" key={path}><code>{path}</code></div>)}
            <h3>模块依赖</h3>
            <div className="tag-row">
              {selected.dependencies.length
                ? selected.dependencies.map((id) => <DependencyTag key={id} id={id} />)
                : <DependencyTag id="no-upstream" label="无上游依赖 · 独立入口" />}
            </div>
          </div>
        </div>
        <h3>指定验收项</h3>
        <div className="check-list">
          {selected.checks.map((check) => (
            <div className="check-row" key={check.id}>
              <span><strong>{check.name}</strong><code>{check.command}</code></span>
              <span className="check-meta">{check.duration_ms} ms <StatusTag status={check.status} /></span>
            </div>
          ))}
        </div>
      </section>
      <Drawer
        title={source ? `${source.path} · ${sourceDescription(source.path)}` : "源码"}
        size={900}
        open={source !== null}
        onClose={() => setSource(null)}
        destroyOnHidden
        extra={source?.path.endsWith(".md") ? (
          <MarkdownDownloadButton content={source.content} filename={source.path.split("/").pop() || "source.md"} />
        ) : undefined}
      >
        {loading && <Spin />}
        {error && <Alert type="error" showIcon title={error} />}
        {!loading && !error && source && <CodeViewer path={source.path} content={source.content} />}
      </Drawer>
    </div>
  )
}
