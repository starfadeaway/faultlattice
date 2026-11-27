import { useEffect, useRef, useState } from "react"
import { DownloadOutlined, MoonOutlined, ReloadOutlined, SunOutlined, UploadOutlined } from "@ant-design/icons"
import { Alert, Button, Segmented, Select, Switch, Tag } from "antd"
import { api } from "../api"
import type { ModelOption } from "../types"
import { formatDateTime, type TimeDisplay } from "../utils/dateTime"

type ThemeMode = "dark" | "light"
type MotionPreference = "system" | "on" | "off"
type Density = "comfortable" | "compact"
type DefaultPage = "/monitor" | "/experiments" | "/analysis" | "/integrations"
type NavigationMode = "domains" | "pages"
type CodeFontSize = 12 | 13 | 14 | 16

const accentPresets = ["#22d3ee", "#34d399", "#f59e0b", "#fb7185", "#a3e635"]

interface Props {
  mode: ThemeMode
  accent: string
  motionPreference: MotionPreference
  codeFontSize: CodeFontSize
  timeDisplay: TimeDisplay
  density: Density
  defaultPage: DefaultPage
  navigationMode: NavigationMode
  refreshInterval: number
  preloadPages: boolean
  showBackToTop: boolean
  codeWrap: boolean
  highContrast: boolean
  advisorOptionId: string
  completionNotifications: boolean
  autoScrollResults: boolean
  projectVersion: string
  onModeChange: (mode: ThemeMode) => void
  onAccentChange: (accent: string) => void
  onMotionChange: (preference: MotionPreference) => void
  onCodeFontSizeChange: (size: CodeFontSize) => void
  onTimeDisplayChange: (display: TimeDisplay) => void
  onDensityChange: (density: Density) => void
  onDefaultPageChange: (page: DefaultPage) => void
  onNavigationModeChange: (mode: NavigationMode) => void
  onRefreshIntervalChange: (interval: number) => void
  onPreloadPagesChange: (enabled: boolean) => void
  onShowBackToTopChange: (enabled: boolean) => void
  onCodeWrapChange: (enabled: boolean) => void
  onHighContrastChange: (enabled: boolean) => void
  onAdvisorOptionChange: (optionId: string) => void
  onCompletionNotificationsChange: (enabled: boolean) => void
  onAutoScrollResultsChange: (enabled: boolean) => void
  onImport: (payload: unknown) => void
  onReset: () => void
}

export function SettingsView({
  mode,
  accent,
  motionPreference,
  codeFontSize,
  timeDisplay,
  density,
  defaultPage,
  navigationMode,
  refreshInterval,
  preloadPages,
  showBackToTop,
  codeWrap,
  highContrast,
  advisorOptionId,
  completionNotifications,
  autoScrollResults,
  projectVersion,
  onModeChange,
  onAccentChange,
  onMotionChange,
  onCodeFontSizeChange,
  onTimeDisplayChange,
  onDensityChange,
  onDefaultPageChange,
  onNavigationModeChange,
  onRefreshIntervalChange,
  onPreloadPagesChange,
  onShowBackToTopChange,
  onCodeWrapChange,
  onHighContrastChange,
  onAdvisorOptionChange,
  onCompletionNotificationsChange,
  onAutoScrollResultsChange,
  onImport,
  onReset,
}: Props) {
  const [backendStatus, setBackendStatus] = useState("检查中")
  const [agentCount, setAgentCount] = useState<number | null>(null)
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([])
  const [checkedAt, setCheckedAt] = useState<string | null>(null)
  const [preferenceNotice, setPreferenceNotice] = useState("")
  const [preferenceError, setPreferenceError] = useState("")
  const fileInput = useRef<HTMLInputElement>(null)

  async function checkEnvironment() {
    const modelRequest = api.experimentModels().catch(() => [] as ModelOption[])
    try {
      const [, agents, models] = await Promise.all([api.health(), api.externalAgents(), modelRequest])
      setBackendStatus("已连接")
      setAgentCount(agents.length)
      setModelOptions(models)
    } catch {
      setBackendStatus("连接失败")
      setAgentCount(null)
      setModelOptions([])
    } finally {
      setCheckedAt(new Date().toISOString())
    }
  }

  useEffect(() => {
    void checkEnvironment()
  }, [])

  async function changeCompletionNotifications(enabled: boolean) {
    setPreferenceNotice("")
    setPreferenceError("")
    if (!enabled) {
      onCompletionNotificationsChange(false)
      setPreferenceNotice("实验完成系统通知已关闭。")
      return
    }
    if (!("Notification" in window)) {
      setPreferenceError("当前浏览器不支持系统通知；其他实验功能不受影响。")
      return
    }
    try {
      const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission()
      if (permission !== "granted") {
        setPreferenceError(permission === "denied" ? "浏览器已拒绝通知权限，请在浏览器站点设置中允许后重试。" : "尚未获得通知授权，因此未开启系统通知。")
        return
      }
      onCompletionNotificationsChange(true)
      setPreferenceNotice("系统通知已开启；仅在你查看运行中的批次且该批次结束时发送。")
    } catch {
      setPreferenceError("通知授权请求失败，请检查浏览器设置后重试。")
    }
  }

  function exportPreferences() {
    const payload = {
      product: "FaultLattice",
      schema: 1,
      preferences: {
        mode,
        accent,
        motionPreference,
        codeFontSize,
        timeDisplay,
        density,
        defaultPage,
        navigationMode,
        refreshInterval,
        preloadPages,
        showBackToTop,
        codeWrap,
        highContrast,
        advisorOptionId,
        completionNotifications,
        autoScrollResults,
      },
    }
    const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = "faultlattice-preferences.json"
    anchor.click()
    URL.revokeObjectURL(url)
    setPreferenceError("")
    setPreferenceNotice("偏好文件已导出；不包含模型密钥、实验历史或适配器源码。")
  }

  async function importPreferences(file: File) {
    setPreferenceNotice("")
    setPreferenceError("")
    try {
      if (file.size > 32_768) throw new Error("偏好文件不能超过 32 KB")
      const payload: unknown = JSON.parse(await file.text())
      onImport(payload)
      setPreferenceNotice("偏好已导入并立即生效；未修改实验数据或模型密钥。")
    } catch (reason) {
      setPreferenceError(reason instanceof Error ? reason.message : "偏好导入失败")
    }
  }

  return (
    <div className="view-stack settings-view">
      <div className="settings-layout">
        <section className="settings-card">
          <div className="settings-heading">
            <div><span className="section-kicker">APPEARANCE & READING</span><h2>外观与阅读</h2></div>
            <span>自动保存 · 立即生效</span>
          </div>
          <div className="setting-row">
            <div><strong>显示模式</strong><p>选择适合当前环境的明暗配色。</p></div>
            <div className="mode-switch" role="group" aria-label="显示模式">
              <Button icon={<MoonOutlined />} type={mode === "dark" ? "primary" : "default"} onClick={() => onModeChange("dark")}>暗色</Button>
              <Button icon={<SunOutlined />} type={mode === "light" ? "primary" : "default"} onClick={() => onModeChange("light")}>亮色</Button>
            </div>
          </div>
          <div className="setting-row accent-setting">
            <div><strong>强调色</strong><p>用于按钮、当前导航和关键状态；顶部标识线保持蓝色。</p></div>
            <div className="color-presets" role="group" aria-label="预设强调色">
              {accentPresets.map((color) => (
                <button
                  type="button"
                  key={color}
                  className={accent.toLowerCase() === color ? "color-swatch active" : "color-swatch"}
                  style={{ backgroundColor: color }}
                  aria-label={`使用强调色 ${color}`}
                  aria-pressed={accent.toLowerCase() === color}
                  title={color}
                  onClick={() => onAccentChange(color)}
                />
              ))}
              <label className="custom-color" title="自由选择强调色">
                <input type="color" value={accent} onChange={(event) => onAccentChange(event.target.value)} aria-label="自定义强调色" />
                <span>自定义</span>
              </label>
            </div>
          </div>
          <div className="setting-row">
            <div><strong>界面动效</strong><p>跟随系统可减少动态效果；显式开启或关闭会覆盖系统偏好。</p></div>
            <Segmented aria-label="界面动效" value={motionPreference} onChange={(value) => onMotionChange(value as MotionPreference)} options={[{ label: "跟随系统", value: "system" }, { label: "开", value: "on" }, { label: "关", value: "off" }]} />
          </div>
          <div className="setting-row">
            <div><strong>界面密度</strong><p>紧凑模式减少卡片留白与区块间距，适合高密度研发信息。</p></div>
            <Segmented aria-label="界面密度" value={density} onChange={(value) => onDensityChange(value as Density)} options={[{ label: "舒适", value: "comfortable" }, { label: "紧凑", value: "compact" }]} />
          </div>
          <div className="setting-row">
            <div><strong>代码字号</strong><p>调整源码抽屉中的文字大小，不改变代码内容。</p></div>
            <Segmented aria-label="代码字号" value={codeFontSize} onChange={(value) => onCodeFontSizeChange(Number(value) as CodeFontSize)} options={[{ label: "12", value: 12 }, { label: "13", value: 13 }, { label: "14", value: 14 }, { label: "16", value: 16 }]} />
          </div>
          <div className="setting-row">
            <div><strong>长代码自动换行</strong><p>关闭后保留原始缩进和长行，通过横向滚动查看完整代码。</p></div>
            <Switch aria-label="长代码自动换行" checked={codeWrap} checkedChildren="开启" unCheckedChildren="关闭" onChange={onCodeWrapChange} />
          </div>
          <div className="setting-row">
            <div><strong>增强对比度</strong><p>提高次要文字与边框的可见度，不改变主题色和实验状态色。</p></div>
            <Switch aria-label="增强对比度" checked={highContrast} checkedChildren="开启" unCheckedChildren="关闭" onChange={onHighContrastChange} />
          </div>
          <div className="settings-footnote"><span>强调色 {accent.toUpperCase()}</span><code>代码 {codeFontSize}px</code></div>
        </section>

        <section className="settings-card">
          <div className="settings-heading">
            <div><span className="section-kicker">EXPERIMENT PREFERENCES</span><h2>实验与导航</h2></div>
            <span>不改变实验条件</span>
          </div>
          <div className="setting-row">
            <div><strong>时间显示</strong><p>本地时间使用当前设备时区；UTC 便于与原始实验产物对齐。</p></div>
            <Segmented aria-label="时间显示" value={timeDisplay} onChange={(value) => onTimeDisplayChange(value as TimeDisplay)} options={[{ label: "本地时间", value: "local" }, { label: "UTC", value: "utc" }]} />
          </div>
          <div className="setting-row">
            <div><strong>默认首页</strong><p>打开根地址或点击 FaultLattice 品牌时进入所选页面。</p></div>
            <Select className="default-page-select" aria-label="默认首页" value={defaultPage} onChange={(value) => onDefaultPageChange(value as DefaultPage)} options={[{ label: "监测", value: "/monitor" }, { label: "实验", value: "/experiments" }, { label: "分析", value: "/analysis" }, { label: "接入", value: "/integrations" }]} />
          </div>
          <div className="setting-row">
            <div><strong>默认模型</strong><p>用于真实模型 M3 和默认修改建议；M0 不调用模型。运行前仍可在实验页调整。</p></div>
            <Select
              className="default-model-select"
              aria-label="默认模型"
              value={modelOptions.some((option) => option.id === advisorOptionId) ? advisorOptionId : undefined}
              placeholder={modelOptions.length ? "选择默认模型" : "暂无可用对话模型"}
              disabled={!modelOptions.length}
              onChange={onAdvisorOptionChange}
              options={modelOptions.map((option) => ({ value: option.id, label: `${option.label} · ${option.model_id}` }))}
            />
          </div>
          <div className="setting-row">
            <div><strong>实验完成系统通知</strong><p>你正在查看运行中的批次时，执行结束或 Harness 错误会发送一条系统通知；需要浏览器授权。</p></div>
            <Switch aria-label="实验完成系统通知" checked={completionNotifications} checkedChildren="开启" unCheckedChildren="关闭" onChange={(enabled) => void changeCompletionNotifications(enabled)} />
          </div>
          <div className="setting-row">
            <div><strong>启动后自动定位结果</strong><p>开启后，新实验启动即平滑滚动到过程与结果；关闭则停留在当前操作位置。</p></div>
            <Switch aria-label="启动后自动定位结果" checked={autoScrollResults} checkedChildren="开启" unCheckedChildren="关闭" onChange={onAutoScrollResultsChange} />
          </div>
          <div className="setting-row">
            <div><strong>导航形式</strong><p>领域分组保持精简；独立页面把常用功能直接放入主导航，并隐藏重复的监测子页。</p></div>
            <Segmented aria-label="导航形式" value={navigationMode} onChange={(value) => onNavigationModeChange(value as NavigationMode)} options={[{ label: "领域分组", value: "domains" }, { label: "独立页面", value: "pages" }]} />
          </div>
          <div className="setting-row">
            <div><strong>进度刷新间隔</strong><p>控制实验事件和进度轮询频率；不会修改后端任务，也不会重复启动实验。</p></div>
            <Segmented aria-label="进度刷新间隔" value={refreshInterval} onChange={(value) => onRefreshIntervalChange(Number(value))} options={[{ label: "0.5 秒", value: 500 }, { label: "0.8 秒", value: 800 }, { label: "1.5 秒", value: 1500 }]} />
          </div>
          <div className="setting-row">
            <div><strong>空闲时预加载页面</strong><p>开启后在浏览器空闲时加载其他页面；关闭可减少首次流量，但首次切换会稍慢。</p></div>
            <Switch aria-label="空闲时预加载页面" checked={preloadPages} checkedChildren="开启" unCheckedChildren="关闭" onChange={onPreloadPagesChange} />
          </div>
          <div className="setting-row">
            <div><strong>显示回到顶部按钮</strong><p>控制长页面右下角的圆形回顶入口；键盘滚动和浏览器滚动不受影响。</p></div>
            <Switch aria-label="显示回到顶部按钮" checked={showBackToTop} checkedChildren="显示" unCheckedChildren="隐藏" onChange={onShowBackToTopChange} />
          </div>
          <div className="settings-footnote"><span>{formatDateTime(checkedAt, timeDisplay)}</span><code>刷新 {refreshInterval}ms</code></div>
        </section>
      </div>

      <section className="settings-card settings-info environment-card">
        <div className="settings-heading">
          <div><span className="section-kicker">PROJECT ENVIRONMENT</span><h2>环境与偏好诊断</h2></div>
          <Button icon={<ReloadOutlined />} onClick={() => void checkEnvironment()}>重新检查</Button>
        </div>
        <dl className="environment-grid">
          <div><dt>后端连接</dt><dd><Tag color={backendStatus === "已连接" ? "success" : backendStatus === "连接失败" ? "error" : "processing"}>{backendStatus}</Tag></dd></div>
          <div><dt>已登记外部适配器</dt><dd>{agentCount === null ? "暂不可读取" : `${agentCount} 个（仅公开元数据）`}</dd></div>
          <div><dt>可选对话模型</dt><dd>{backendStatus === "已连接" ? `${modelOptions.length} 个（密钥不会返回前端）` : "暂不可读取"}</dd></div>
          <div><dt>当前版本</dt><dd><code>FaultLattice v{projectVersion}</code></dd></div>
          <div><dt>依赖管理</dt><dd><code>uv</code> · <code>pyproject.toml</code> · <code>uv.lock</code></dd></div>
          <div><dt>项目 Python</dt><dd><code>.venv</code> · Pyright 固定使用此环境</dd></div>
          <div><dt>本地预览</dt><dd><code>npm run dev</code> · 前后端保持热更新</dd></div>
          <div><dt>测试与验收</dt><dd><code>uv run pytest</code> · 保留 uv 工作流</dd></div>
          <div><dt>偏好存储</dt><dd>仅当前浏览器 localStorage；不保存或展示密钥</dd></div>
        </dl>
        <div className="preference-backup">
          <div><strong>偏好备份与迁移</strong><p>导出外观、导航、默认模型 ID 和实验交互偏好，或从之前导出的 JSON 恢复。导入会校验字段，不接收密钥或任意配置。</p></div>
          <div className="preference-backup-actions">
            <Button icon={<DownloadOutlined />} onClick={exportPreferences}>导出偏好</Button>
            <Button icon={<UploadOutlined />} onClick={() => fileInput.current?.click()}>导入偏好</Button>
            <input ref={fileInput} className="visually-hidden" type="file" accept="application/json,.json" aria-label="选择偏好 JSON 文件" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importPreferences(file); event.target.value = "" }} />
          </div>
        </div>
        {preferenceNotice && <Alert type="success" showIcon title={preferenceNotice} />}
        {preferenceError && <Alert type="error" showIcon title={preferenceError} />}
        <div className="settings-reset-row">
          <p>恢复默认会重置外观、导航、通知和实验交互，保留默认模型选择；不删除实验历史、模型密钥或适配器登记。</p>
          <Button onClick={onReset}>恢复默认设置</Button>
        </div>
      </section>
    </div>
  )
}
