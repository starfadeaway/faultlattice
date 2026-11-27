import { ArrowRightOutlined, BranchesOutlined } from "@ant-design/icons"
import { Typography } from "antd"
import type { ProjectModule, ProjectSnapshot } from "../types"
import { StatusTag } from "../components/StatusTag"
import { DependencyTag } from "../components/DependencyTag"
import { toneFor } from "../utils/dependencyTone"

interface Props {
  data: ProjectSnapshot
  onSelectModule: (id: string) => void
}

export function ProjectMap({ data, onSelectModule }: Props) {
  const moduleNames = new Map(data.modules.map((module) => [module.id, module.name]))
  return (
    <div className="view-stack">
      <div className="section-heading">
        <div>
          <span className="section-kicker">PROJECT MAP</span>
          <h2>从代码到验收的依赖地图</h2>
        </div>
        <Typography.Text type="secondary">点击模块进入源码与验收明细</Typography.Text>
      </div>
      <div className="map-layout">
        <div className="dependency-map">
          {data.modules.map((module: ProjectModule) => (
            <button
              type="button"
              className={`module-node module-tone-${toneFor(module.id)}`}
              key={module.id}
              onClick={() => onSelectModule(module.id)}
            >
              <span className="module-node-top">
                <span className="module-icon"><BranchesOutlined /></span>
                <StatusTag status={module.status} />
              </span>
              <strong>{module.name}</strong>
              <code>{module.source_paths[0]}</code>
              <span className="module-dependencies">
                <span className="dependency-tags">
                  {module.dependencies.length
                    ? module.dependencies.map((id) => <DependencyTag key={id} id={id} label={moduleNames.get(id)} />)
                    : <DependencyTag id="no-upstream" label="无上游依赖 · 独立入口" />}
                </span>
                <ArrowRightOutlined />
              </span>
            </button>
          ))}
        </div>
        <aside className="project-facts">
          <span className="section-kicker">CURRENT PROJECT</span>
          <h3>{data.project.name}</h3>
          <p>{data.project.subtitle}</p>
          <dl>
            <div><dt>包版本</dt><dd>v{data.project.version}</dd></div>
            <div><dt>登记模块</dt><dd>{data.modules.length} 个</dd></div>
            <div><dt>项目清单</dt><dd><code>{data.project.manifest}</code></dd></div>
            <div><dt>当前工作区</dt><dd><code>{data.project.name}</code>（自动识别）</dd></div>
          </dl>
        </aside>
      </div>
    </div>
  )
}
