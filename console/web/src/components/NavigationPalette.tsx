import { Modal } from "antd"
import { Command } from "cmdk"

export interface NavigationEntry {
  path: string
  title: string
  group: "实验工作流" | "研发监测" | "系统"
  description: string
  keywords: string
}

const navigationEntries: NavigationEntry[] = [
  { path: "/experiments", title: "实验与一键测试", group: "实验工作流", description: "选择内置套件或已登记 Agent，运行兼容任务并查看结果", keywords: "测试 运行 实验对象 套件 结果 建议" },
  { path: "/analysis", title: "实验分析", group: "实验工作流", description: "跨批次聚合真实历史、分层 Oracle 分布与任务对比，可下载分析 Markdown", keywords: "分析 聚合 筛选 分布 对比 沉默失败 下载" },
  { path: "/integrations?section=hosts", title: "已登记实验对象", group: "实验工作流", description: "查看预检通过的宿主、能力、源码和兼容任务", keywords: "agent 宿主 适配器 已登记 预检" },
  { path: "/integrations?section=register", title: "接入新 Agent", group: "实验工作流", description: "上传可信适配器或使用 AI 草案，完成真实登记", keywords: "导入 上传 接入 agent readme 适配器" },
  { path: "/integrations?section=tasks", title: "任务创作与队列", group: "实验工作流", description: "上传任务文件、生成标准任务包或创建自定义任务", keywords: "任务 自定义 上传 yaml ai 队列" },
  { path: "/monitor", title: "监测首页", group: "研发监测", description: "项目健康度、验收入口与最近运行概览", keywords: "首页 健康度 概览" },
  { path: "/map", title: "项目地图", group: "研发监测", description: "查看模块依赖、工程身份与源码导航", keywords: "依赖 拓扑 架构 模块" },
  { path: "/modules", title: "模块与代码", group: "研发监测", description: "浏览源码、语法高亮和逐文件中文说明", keywords: "代码 源码 文件 python typescript" },
  { path: "/checks", title: "测试与静态检查", group: "研发监测", description: "查看真实命令、退出码、耗时和完整输出", keywords: "pytest ruff pyright 测试 检查" },
  { path: "/artifacts", title: "实验产物与报告", group: "研发监测", description: "复核运行四件套，阅读或下载 Markdown 报告", keywords: "报告 产物 markdown 下载 历史" },
  { path: "/naming", title: "命名登记", group: "研发监测", description: "检索项目术语、接口名称和变更约束", keywords: "naming 术语 文档 命名" },
  { path: "/settings", title: "设置", group: "系统", description: "外观、动效、代码阅读、默认首页和偏好备份", keywords: "主题 明暗 颜色 设置 偏好" },
]

interface NavigationPaletteProps {
  open: boolean
  onClose: () => void
  onNavigate: (path: string) => void
}

export function NavigationPalette({ open, onClose, onNavigate }: NavigationPaletteProps) {
  const groups = ["实验工作流", "研发监测", "系统"] as const
  return (
    <Modal
      className="navigation-modal"
      title="查找页面与功能"
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      <Command label="页面与功能搜索">
        <Command.Input autoFocus placeholder="输入“外部 Agent”“报告”“测试”等关键词……" aria-label="搜索页面与功能" />
        <Command.List>
          <Command.Empty>没有匹配的功能。可以尝试“实验”“接入”或“报告”。</Command.Empty>
          {groups.map((group) => (
            <Command.Group heading={group} key={group}>
              {navigationEntries.filter((entry) => entry.group === group).map((entry) => (
                <Command.Item
                  key={entry.path}
                  value={`${entry.title} ${entry.description} ${entry.keywords}`}
                  onSelect={() => {
                    onNavigate(entry.path)
                    onClose()
                  }}
                >
                  <span className="command-item-copy"><strong>{entry.title}</strong><small>{entry.description}</small></span>
                  <code>{entry.path}</code>
                </Command.Item>
              ))}
            </Command.Group>
          ))}
        </Command.List>
        <div className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> 选择</span><span><kbd>Enter</kbd> 打开</span><span><kbd>Esc</kbd> 关闭</span></div>
      </Command>
    </Modal>
  )
}
