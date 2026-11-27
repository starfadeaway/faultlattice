export async function readUtf8File(file: File, maxCharacters = 100_000): Promise<string> {
  let content: string
  try {
    content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer())
  } catch {
    throw new Error(`${file.name} 不是有效的 UTF-8 文本文件`)
  }
  if (!content.trim()) throw new Error(`${file.name} 是空文件`)
  if (content.length > maxCharacters) {
    throw new Error(`${file.name} 超过 ${maxCharacters.toLocaleString()} 字符上限`)
  }
  return content
}

export function downloadText(filename: string, content: string, type = "text/plain;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
