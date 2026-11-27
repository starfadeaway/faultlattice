import {
  ApartmentOutlined,
  ApiOutlined,
  ArrowRightOutlined,
  BookOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
} from "@ant-design/icons"
import type { CSSProperties } from "react"
import { NavLink } from "react-router"
import type { Artifact, ProjectSnapshot } from "../types"

const monitorViews = [
  { path: "/map", title: "项目地图", description: "查看模块依赖和项目工程身份", icon: <ApartmentOutlined /> },
  { path: "/modules", title: "模块与代码", description: "浏览带行号、语法分色和中文说明的源码", icon: <ApiOutlined /> },
  { path: "/checks", title: "测试状态", description: "核对真实命令、退出码、耗时和输出", icon: <CheckCircleOutlined /> },
  { path: "/naming", title: "命名登记", description: "阅读并下载具有契约含义的名称登记", icon: <BookOutlined /> },
  { path: "/artifacts", title: "实验产物", description: "查看运行四件套并下载 Markdown 报告", icon: <ExperimentOutlined /> },
]

interface Props {
  data: ProjectSnapshot
  artifacts: Artifact[]
  onPreload: (path: string) => void
}

export function MonitorHome({ data, artifacts, onPreload }: Props) {
  const healthy = data.summary.passed_checks === data.summary.checks
  return (
    <div className="view-stack monitor-home">
      <section className="monitor-hero">
        <div>
          <span className="section-kicker">PROJECT HEALTH</span>
          <h2>{healthy ? "当前项目验收通过" : "当前项目存在待处理项"}</h2>
          <p>这里汇总项目状态；进入下方视图可查看代码、测试与实验证据。</p>
        </div>
        <div className="hero-status"><span className={healthy ? "live-dot" : "live-dot is-offline"} />{healthy ? "验收状态正常" : "需要检查失败项"}</div>
      </section>
      <section className="monitor-entry-section" aria-labelledby="monitor-entry-title">
        <div className="section-heading">
          <div><span className="section-kicker">MONITORING VIEWS</span><h2 id="monitor-entry-title">监测视图</h2></div>
          <span>{artifacts.length} 次实验运行已登记</span>
        </div>
        <div className="monitor-entry-grid">
          {monitorViews.map((view, index) => (
            <NavLink
              to={view.path}
              className="monitor-entry"
              key={view.path}
              style={{ "--entry-index": index } as CSSProperties}
              onMouseEnter={() => onPreload(view.path)}
              onFocus={() => onPreload(view.path)}
            >
              <span className="monitor-entry-icon">{view.icon}</span>
              <strong>{view.title}</strong>
              <p>{view.description}</p>
              <span className="monitor-entry-action">进入视图 <ArrowRightOutlined /></span>
            </NavLink>
          ))}
        </div>
      </section>
    </div>
  )
}
