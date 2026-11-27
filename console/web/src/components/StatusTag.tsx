import { CheckCircleFilled, ClockCircleFilled, CloseCircleFilled } from "@ant-design/icons"
import { Tag } from "antd"

export function StatusTag({ status }: { status: "verified" | "developing" | "passed" | "failed" }) {
  const config = {
    verified: { color: "success", icon: <CheckCircleFilled />, text: "已验证" },
    developing: { color: "warning", icon: <ClockCircleFilled />, text: "开发中" },
    passed: { color: "success", icon: <CheckCircleFilled />, text: "通过" },
    failed: { color: "error", icon: <CloseCircleFilled />, text: "失败" },
  }[status]
  return <Tag color={config.color} icon={config.icon}>{config.text}</Tag>
}
