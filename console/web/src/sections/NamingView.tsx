import { useEffect, useState } from "react"
import { Alert, Spin } from "antd"
import ReactMarkdown from "react-markdown"
import rehypeSlug from "rehype-slug"
import remarkGfm from "remark-gfm"
import { api } from "../api"
import { MarkdownDownloadButton } from "../components/MarkdownDownloadButton"

export function NamingView() {
  const [content, setContent] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.naming().then((result) => setContent(result.content)).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "命名登记读取失败")
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="view-loading"><Spin description="正在读取命名登记" /></div>
  if (error) return <Alert type="error" showIcon title={error} />
  return (
    <div>
      <div className="document-toolbar">
        <span>docs/NAMING.md</span>
        <MarkdownDownloadButton content={content} filename="FaultLattice-NAMING.md" />
      </div>
      <div className="document-view">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} components={{
          a: ({ href, children }) => href?.startsWith("#")
            ? <a className="document-anchor-link" href={href}>{children}</a>
            : <span className="document-local-link">{children}</span>,
        }}>{content}</ReactMarkdown>
      </div>
    </div>
  )
}
