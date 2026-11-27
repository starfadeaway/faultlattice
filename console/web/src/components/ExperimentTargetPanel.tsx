import { PlayCircleOutlined, PlusOutlined } from "@ant-design/icons"
import { Alert, Button, Empty, Select, Tag } from "antd"
import type { ExternalAgent } from "../types"

interface ExperimentTargetPanelProps {
  agents: ExternalAgent[]
  targetId: string
  taskPath: string
  starting: boolean
  modelConfigured: boolean
  onTargetChange: (value: string) => void
  onTaskChange: (value: string) => void
  onRun: () => Promise<void>
  onOpenIntegrations: (section: "tasks" | "hosts") => void
}

export function ExperimentTargetPanel({
  agents,
  targetId,
  taskPath,
  starting,
  modelConfigured,
  onTargetChange,
  onTaskChange,
  onRun,
  onOpenIntegrations,
}: ExperimentTargetPanelProps) {
  const selectedAgent = agents.find((agent) => agent.id === targetId) || null
  const selectedTask = selectedAgent?.compatible_tasks.find((task) => task.path === taskPath) || null

  return (
    <section className="target-workbench" aria-labelledby="experiment-target-heading">
      <div className="section-heading">
        <div>
          <span className="section-kicker">STEP 1 / TEST SUBJECT</span>
          <h2 id="experiment-target-heading">先选择本次要测试的对象</h2>
        </div>
        <Button icon={<PlusOutlined />} onClick={() => onOpenIntegrations("hosts")}>管理实验对象</Button>
      </div>
      <div className="target-workbench-intro">
        <p><strong>实验对象不是上传适配器后自动生成的。</strong>只有“接入”页中已登记、真实加载且 preflight 通过的 Agent 才会进入下方选项；AI 草案或仅上传的文件不会出现在这里。</p>
        <ol className="target-source-flow" aria-label="外部实验对象生成流程">
          <li><b>1</b><span>保存适配器</span></li>
          <li><b>2</b><span>登记并真实加载</span></li>
          <li><b>3</b><span>preflight 通过后可选</span></li>
        </ol>
        <p>选择外部 Agent 后，系统再按执行模式、工具声明、故障注入点和 preflight 自动匹配兼容任务；不匹配的内置任务不会强行运行。</p>
      </div>
      <div className="target-picker-row">
        <label>
          <span>实验对象</span>
          <Select
            aria-label="实验对象"
            value={targetId}
            showSearch
            optionFilterProp="label"
            options={[
              {
                label: "标准测试",
                options: [{ value: "builtin", label: "内置参考宿主与标准套件" }],
              },
              {
                label: `我的外部 Agent（${agents.length}）`,
                options: agents.map((agent) => ({
                  value: agent.id,
                  label: `${agent.name} · ${agent.host_name || agent.class_name}`,
                })),
              },
            ]}
            onChange={onTargetChange}
          />
        </label>
        <div className="target-selection-summary">
          {selectedAgent ? (
            <>
              <Tag color="success">预检通过</Tag>
              <strong>{selectedAgent.name}</strong>
              <code>{selectedAgent.entrypoint} · {selectedAgent.class_name}</code>
            </>
          ) : (
            <>
              <Tag color="blue">标准套件</Tag>
              <strong>按下方套件组织多项预注册实验</strong>
              <span>套件仍是一键自动执行；这里不需要手工出题。</span>
            </>
          )}
        </div>
      </div>

      {selectedAgent && (
        <div className="external-run-workbench">
          <div className="capability-tags">
            <Tag color="blue">{selectedAgent.host_name} · v{selectedAgent.host_package_version || "未声明"}</Tag>
            {selectedAgent.capabilities?.modes.map((mode) => <Tag key={mode}>{mode}</Tag>)}
            {selectedAgent.capabilities?.injection_points.map((point) => <Tag color="purple" key={point}>{point}</Tag>)}
            {selectedAgent.capabilities?.tools.map((tool) => <Tag color="cyan" key={tool}>工具：{tool}</Tag>)}
          </div>
          <div className="external-run-grid">
            <div className="external-run-picker">
              <span className="section-kicker">STEP 2 / COMPATIBLE TASK</span>
              <label>
                <span>兼容的预注册任务（{selectedAgent.compatible_tasks.length}）</span>
                <Select
                  aria-label="外部 Agent 兼容任务"
                  value={selectedTask?.path}
                  placeholder="没有兼容任务"
                  disabled={!selectedAgent.compatible_tasks.length}
                  showSearch
                  optionFilterProp="label"
                  options={selectedAgent.compatible_tasks.map((task) => ({
                    value: task.path,
                    label: `${task.task_id} · ${task.mode} · ${task.description}`,
                  }))}
                  onChange={onTaskChange}
                />
              </label>
              <small>任务列表由宿主实际能力、工具声明和 preflight 自动筛选，不会拿不匹配的内置任务强行测试。</small>
            </div>
            <div className="external-run-action">
              <span className="section-kicker">STEP 3 / RUN & REVIEW</span>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={starting}
                disabled={!selectedTask || (selectedTask.mode === "M3" && !modelConfigured)}
                onClick={() => void onRun()}
                block
              >
                运行所选任务并查看全过程
              </Button>
              <small>{selectedTask?.mode === "M3" ? "将使用上方选定的真实模型，并在启动时冻结配置。" : "M0 不调用真实模型；结束后仍可生成修改建议。"}</small>
            </div>
          </div>
          {!selectedAgent.compatible_tasks.length && (
            <Alert
              type="warning"
              showIcon
              title="当前宿主没有兼容任务"
              description="可以先创建符合其工具与执行模式的任务，再返回本页运行。"
              action={<Button size="small" onClick={() => onOpenIntegrations("tasks")}>创建兼容任务</Button>}
            />
          )}
          {selectedTask ? (
            <div className="selected-external-task">
              <div><Tag color={selectedTask.origin === "custom" ? "purple" : "blue"}>{selectedTask.origin === "custom" ? "自定义任务" : "内置自检"}</Tag><code>{selectedTask.path}</code></div>
              <strong>{selectedTask.description}</strong>
              <p><b>任务目标：</b>{selectedTask.expected_behavior}</p>
              <dl>
                <div><dt>执行模式</dt><dd>{selectedTask.mode}</dd></div>
                <div><dt>评价层</dt><dd>{selectedTask.target_layers.join(" / ")}</dd></div>
                <div><dt>故障契约</dt><dd>{selectedTask.fault ? `${String(selectedTask.fault.injection_point)} / ${String(selectedTask.fault.fault_type)} / ${String(selectedTask.fault.surface_as)}` : "无故障基线"}</dd></div>
              </dl>
            </div>
          ) : (
            <Empty description="选择或创建一个兼容任务后即可运行" />
          )}
        </div>
      )}
    </section>
  )
}
