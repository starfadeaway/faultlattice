import { Collapse, Typography } from "antd"
import type { CheckResult } from "../types"
import { StatusTag } from "../components/StatusTag"

export function ChecksView({ checks }: { checks: CheckResult[] }) {
  return (
    <div className="view-stack">
      <div className="section-heading">
        <div><span className="section-kicker">REQUIRED CHECKS</span><h2>测试与验收状态</h2></div>
        <Typography.Text type="secondary">每次刷新都会执行真实命令，不使用缓存结论</Typography.Text>
      </div>
      <Collapse
        className="checks-collapse"
        items={checks.map((check) => ({
          key: check.id,
          label: <span className="check-collapse-label"><strong>{check.name}</strong><code>{check.command}</code></span>,
          extra: <span className="check-meta">{check.duration_ms} ms <StatusTag status={check.status} /></span>,
          children: (
            <div>
              <p>退出码：<strong>{check.returncode}</strong></p>
              <pre className="check-output">{check.output || "命令没有输出。"}</pre>
            </div>
          ),
        }))}
      />
    </div>
  )
}
