import { toneFor } from "../utils/dependencyTone"

interface DependencyTagProps {
  id: string
  label?: string
}

export function DependencyTag({ id, label }: DependencyTagProps) {
  const title = id === "no-upstream" ? "这是独立入口模块，不依赖其他项目模块" : `依赖模块：${id}`
  return <span className={`dependency-chip dependency-${toneFor(id)}`} title={title}>{label || id}</span>
}
