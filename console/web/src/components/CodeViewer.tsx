import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter"
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism"
import python from "react-syntax-highlighter/dist/esm/languages/prism/python"
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript"
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx"
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript"
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx"
import json from "react-syntax-highlighter/dist/esm/languages/prism/json"
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml"
import markdown from "react-syntax-highlighter/dist/esm/languages/prism/markdown"
import css from "react-syntax-highlighter/dist/esm/languages/prism/css"

SyntaxHighlighter.registerLanguage("python", python)
SyntaxHighlighter.registerLanguage("typescript", typescript)
SyntaxHighlighter.registerLanguage("tsx", tsx)
SyntaxHighlighter.registerLanguage("javascript", javascript)
SyntaxHighlighter.registerLanguage("jsx", jsx)
SyntaxHighlighter.registerLanguage("json", json)
SyntaxHighlighter.registerLanguage("yaml", yaml)
SyntaxHighlighter.registerLanguage("markdown", markdown)
SyntaxHighlighter.registerLanguage("css", css)

const languages: Record<string, string> = {
  py: "python",
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  md: "markdown",
  css: "css",
}

const languageLabels: Record<string, string> = {
  py: "Python",
  ts: "TypeScript",
  tsx: "TypeScript / TSX",
  js: "JavaScript",
  jsx: "JavaScript / JSX",
  json: "JSON",
  yaml: "YAML",
  yml: "YAML",
  md: "Markdown",
  css: "CSS",
}

export function CodeViewer({ path, content }: { path: string; content: string }) {
  const extension = path.split(".").pop()?.toLowerCase() || "text"
  return (
    <figure className="code-frame">
      <figcaption><strong>{languageLabels[extension] || "Plain Text"}</strong><code>{path.split("/").pop()}</code></figcaption>
      <SyntaxHighlighter
        language={languages[extension] || "text"}
        style={oneDark}
        showLineNumbers
        wrapLongLines={document.documentElement.dataset.codeWrap !== "off"}
        className="code-view"
        codeTagProps={{ style: { fontFamily: "var(--component-code-font)" } }}
        customStyle={{ background: "#0b1119", margin: 0, padding: "18px" }}
        lineNumberStyle={{ color: "#607285", minWidth: "3em", paddingRight: "1.5em" }}
      >
        {content}
      </SyntaxHighlighter>
    </figure>
  )
}
