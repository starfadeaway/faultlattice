import { DownloadOutlined } from "@ant-design/icons"
import { Button } from "antd"
import { downloadMarkdown } from "../utils/downloadMarkdown"

interface Props {
  content: string
  filename: string
  loading?: boolean
  disabled?: boolean
  onClick?: () => void
}

export function MarkdownDownloadButton({ content, filename, loading, disabled, onClick }: Props) {
  return (
    <Button
      icon={<DownloadOutlined />}
      loading={loading}
      disabled={disabled || !content}
      onClick={() => {
        downloadMarkdown(filename, content)
        onClick?.()
      }}
    >
      下载 Markdown
    </Button>
  )
}
