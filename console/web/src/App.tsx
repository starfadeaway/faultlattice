import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ApartmentOutlined,
  ApiOutlined,
  BarChartOutlined,
  BookOutlined,
  CheckCircleOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
} from "@ant-design/icons"
import { Alert, Button, ConfigProvider, Spin, theme as antdTheme } from "antd"
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router"
import { api } from "./api"
import { BackToTop } from "./components/BackToTop"
import { NavigationPalette } from "./components/NavigationPalette"
import type { Artifact, ProjectSnapshot } from "./types"
import { formatDateTime, storedTimeDisplay, type TimeDisplay } from "./utils/dateTime"
import "./App.css"

const importMonitorHome = () => import("./sections/MonitorHome")
const importProjectMap = () => import("./sections/ProjectMap")
const importModulesView = () => import("./sections/ModulesView")
const importChecksView = () => import("./sections/ChecksView")
const importNamingView = () => import("./sections/NamingView")
const importArtifactsView = () => import("./sections/ArtifactsView")
const importExperimentsView = () => import("./sections/ExperimentsView")
const importAnalyticsView = () => import("./sections/AnalyticsView")
const importExternalAgentsView = () => import("./sections/ExternalAgentsView")
const importSettingsView = () => import("./sections/SettingsView")

const MonitorHome = lazy(() => importMonitorHome().then((module) => ({ default: module.MonitorHome })))
const ProjectMap = lazy(() => importProjectMap().then((module) => ({ default: module.ProjectMap })))
const ModulesView = lazy(() => importModulesView().then((module) => ({ default: module.ModulesView })))
const ChecksView = lazy(() => importChecksView().then((module) => ({ default: module.ChecksView })))
const NamingView = lazy(() => importNamingView().then((module) => ({ default: module.NamingView })))
const ArtifactsView = lazy(() => importArtifactsView().then((module) => ({ default: module.ArtifactsView })))
const ExperimentsView = lazy(() => importExperimentsView().then((module) => ({ default: module.ExperimentsView })))
const AnalyticsView = lazy(() => importAnalyticsView().then((module) => ({ default: module.AnalyticsView })))
const ExternalAgentsView = lazy(() => importExternalAgentsView().then((module) => ({ default: module.ExternalAgentsView })))
const SettingsView = lazy(() => importSettingsView().then((module) => ({ default: module.SettingsView })))

const routeLoaders: Record<string, () => Promise<unknown>> = {
  "/monitor": importMonitorHome,
  "/map": importProjectMap,
  "/modules": importModulesView,
  "/checks": importChecksView,
  "/naming": importNamingView,
  "/artifacts": importArtifactsView,
  "/experiments": importExperimentsView,
  "/analysis": importAnalyticsView,
  "/integrations": importExternalAgentsView,
  "/settings": importSettingsView,
}

type ThemeMode = "dark" | "light"
type MotionPreference = "system" | "on" | "off"
type Density = "comfortable" | "compact"
type DefaultPage = "/monitor" | "/experiments" | "/analysis" | "/integrations"
type NavigationMode = "domains" | "pages"

const monitorNavigation = [
  { path: "/map", label: "项目地图", icon: <ApartmentOutlined />, load: importProjectMap },
  { path: "/modules", label: "模块与代码", icon: <ApiOutlined />, load: importModulesView },
  { path: "/checks", label: "测试状态", icon: <CheckCircleOutlined />, load: importChecksView },
  { path: "/artifacts", label: "实验产物", icon: <ExperimentOutlined />, load: importArtifactsView },
  { path: "/naming", label: "命名登记", icon: <BookOutlined />, load: importNamingView },
]

const primaryNavigation = [
  { path: "/monitor", label: "监测", icon: <DashboardOutlined />, load: importMonitorHome },
  { path: "/experiments", label: "实验", icon: <ExperimentOutlined />, load: importExperimentsView },
  { path: "/analysis", label: "分析", icon: <BarChartOutlined />, load: importAnalyticsView },
  { path: "/integrations", label: "接入", icon: <DeploymentUnitOutlined />, load: importExternalAgentsView },
  { path: "/settings", label: "设置", icon: <SettingOutlined />, load: importSettingsView },
]

const pageNavigation = [
  ...primaryNavigation.slice(0, 3),
  ...monitorNavigation,
  ...primaryNavigation.slice(3),
]

const pageCopy: Record<string, { title: string; subtitle: string; code: string }> = {
  "/monitor": { title: "监测首页", subtitle: "项目健康度、验收入口与实验运行总览", code: "MONITOR / OVERVIEW" },
  "/map": { title: "项目地图", subtitle: "模块依赖、工程身份与源码导航", code: "MONITOR / TOPOLOGY" },
  "/modules": { title: "模块与代码", subtitle: "源码导航、语法高亮与模块验收证据", code: "MONITOR / SOURCE" },
  "/checks": { title: "测试状态", subtitle: "真实命令、退出码、耗时与完整输出", code: "MONITOR / CHECKS" },
  "/naming": { title: "命名登记", subtitle: "项目术语、接口名称与变更约束", code: "MONITOR / NAMING" },
  "/artifacts": { title: "实验产物", subtitle: "原始运行四件套与可下载实验报告", code: "MONITOR / ARTIFACTS" },
  "/experiments": { title: "实验视图", subtitle: "选择内置套件或外部 Agent，运行兼容任务并复核结果", code: "EXPERIMENTS / LIVE" },
  "/analysis": { title: "实验分析", subtitle: "动态图表、规则结论、跨批次模型分析与 Markdown 输出", code: "ANALYSIS / EVIDENCE" },
  "/integrations": { title: "Agent 接入", subtitle: "登记外部宿主、真实预检并运行兼容任务", code: "AGENTS / INTEGRATIONS" },
  "/settings": { title: "设置", subtitle: "管理控制台外观、实验流程与本机偏好", code: "CONSOLE / SETTINGS" },
}

function storedValue(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

type CodeFontSize = 12 | 13 | 14 | 16

function storedCodeFontSize(): CodeFontSize {
  const value = Number(storedValue("faultlattice-code-font-size"))
  return [12, 13, 14, 16].includes(value) ? value as CodeFontSize : 13
}

function storedBoolean(key: string, fallback: boolean): boolean {
  const stored = storedValue(key)
  return stored === "true" ? true : stored === "false" ? false : fallback
}

export default function App() {
  const [data, setData] = useState<ProjectSnapshot | null>(null)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [selectedModule, setSelectedModule] = useState("core")
  const [mode, setMode] = useState<ThemeMode>(() => storedValue("faultlattice-theme") === "light" ? "light" : "dark")
  const [accent, setAccent] = useState(() => storedValue("faultlattice-accent") || "#22d3ee")
  const [motionPreference, setMotionPreference] = useState<MotionPreference>(() => {
    const stored = storedValue("faultlattice-motion")
    return stored === "off" || stored === "on" ? stored : "system"
  })
  const [systemReducedMotion, setSystemReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  const [codeFontSize, setCodeFontSize] = useState<CodeFontSize>(storedCodeFontSize)
  const [timeDisplay, setTimeDisplay] = useState<TimeDisplay>(storedTimeDisplay)
  const [density, setDensity] = useState<Density>(() => storedValue("faultlattice-density") === "compact" ? "compact" : "comfortable")
  const [defaultPage, setDefaultPage] = useState<DefaultPage>(() => {
    const stored = storedValue("faultlattice-default-page")
    return stored === "/experiments" || stored === "/analysis" || stored === "/integrations" ? stored : "/monitor"
  })
  const [navigationMode, setNavigationMode] = useState<NavigationMode>(
    () => storedValue("faultlattice-navigation-mode") === "pages" ? "pages" : "domains",
  )
  const [refreshInterval, setRefreshInterval] = useState(() => {
    const stored = Number(storedValue("faultlattice-refresh-interval"))
    return [500, 800, 1500].includes(stored) ? stored : 800
  })
  const [preloadPages, setPreloadPages] = useState(() => storedBoolean("faultlattice-preload-pages", true))
  const [showBackToTop, setShowBackToTop] = useState(() => storedBoolean("faultlattice-show-back-to-top", true))
  const [codeWrap, setCodeWrap] = useState(() => storedBoolean("faultlattice-code-wrap", true))
  const [highContrast, setHighContrast] = useState(() => storedBoolean("faultlattice-high-contrast", false))
  const [advisorOptionId, setAdvisorOptionId] = useState(() => storedValue("faultlattice.advisor-option") || "")
  const [completionNotifications, setCompletionNotifications] = useState(() => storedBoolean("faultlattice-completion-notifications", false) && "Notification" in window && Notification.permission === "granted")
  const [autoScrollResults, setAutoScrollResults] = useState(() => storedBoolean("faultlattice-auto-scroll-results", true))
  const [loading, setLoading] = useState(true)
  const [navigationOpen, setNavigationOpen] = useState(false)
  const [error, setError] = useState("")
  const [artifactError, setArtifactError] = useState("")
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const initialLoad = useRef(false)
  const location = useLocation()
  const navigate = useNavigate()
  const page = pageCopy[location.pathname] || pageCopy["/monitor"]
  const isSettings = location.pathname === "/settings"
  const isExperiments = location.pathname === "/experiments"
  const isAnalytics = location.pathname === "/analysis"
  const isIntegrations = location.pathname === "/integrations"
  const isRoot = location.pathname === "/"
  const isStandalone = isExperiments || isAnalytics || isIntegrations || isSettings || isRoot
  const isMonitor = !isStandalone
  const isMonitorHome = location.pathname === "/monitor"
  const motionEnabled = motionPreference === "on" || (motionPreference === "system" && !systemReducedMotion)

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError("")
    setArtifactError("")
    const [projectResult, artifactResult] = await Promise.allSettled([api.project(), api.artifacts()])
    if (projectResult.status === "fulfilled") {
      setData(projectResult.value)
    } else {
      setError(projectResult.reason instanceof Error ? projectResult.reason.message : "项目状态读取失败")
    }
    if (artifactResult.status === "fulfilled") {
      setArtifacts(artifactResult.value)
    } else {
      setArtifactError(artifactResult.reason instanceof Error ? artifactResult.reason.message : "产物读取失败")
    }
    setLastUpdated(new Date())
    setLoading(false)
  }, [])

  useEffect(() => {
    if (initialLoad.current || isStandalone) return
    initialLoad.current = true
    // 实验与接入页直接读取自己的服务，不等待研发验收；切到监测页时再加载。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadAll()
  }, [isStandalone, loadAll])

  useEffect(() => {
    document.documentElement.dataset.theme = mode
    document.documentElement.style.setProperty("--accent", accent)
    try {
      window.localStorage.setItem("faultlattice-theme", mode)
      window.localStorage.setItem("faultlattice-accent", accent)
    } catch {
      // 隐私模式下存储不可用时仍保留本次会话的主题设置。
    }
  }, [mode, accent])

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const update = () => setSystemReducedMotion(media.matches)
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setNavigationOpen((current) => !current)
      }
    }
    window.addEventListener("keydown", handleShortcut)
    return () => window.removeEventListener("keydown", handleShortcut)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.motion = motionEnabled ? "on" : "off"
    document.documentElement.dataset.density = density
    document.documentElement.dataset.codeWrap = codeWrap ? "on" : "off"
    document.documentElement.dataset.contrast = highContrast ? "high" : "normal"
    document.documentElement.style.setProperty("--code-font-size", `${codeFontSize}px`)
    try {
      window.localStorage.setItem("faultlattice-motion", motionPreference)
      window.localStorage.setItem("faultlattice-code-font-size", String(codeFontSize))
      window.localStorage.setItem("faultlattice-time-display", timeDisplay)
      window.localStorage.setItem("faultlattice-density", density)
      window.localStorage.setItem("faultlattice-default-page", defaultPage)
      window.localStorage.setItem("faultlattice-navigation-mode", navigationMode)
      window.localStorage.setItem("faultlattice-refresh-interval", String(refreshInterval))
      window.localStorage.setItem("faultlattice-preload-pages", String(preloadPages))
      window.localStorage.setItem("faultlattice-show-back-to-top", String(showBackToTop))
      window.localStorage.setItem("faultlattice-code-wrap", String(codeWrap))
      window.localStorage.setItem("faultlattice-high-contrast", String(highContrast))
      window.localStorage.setItem("faultlattice.advisor-option", advisorOptionId)
      window.localStorage.setItem("faultlattice-completion-notifications", String(completionNotifications))
      window.localStorage.setItem("faultlattice-auto-scroll-results", String(autoScrollResults))
    } catch {
      // 存储不可用时仍在当前会话中应用全部偏好。
    }
  }, [motionEnabled, motionPreference, codeFontSize, timeDisplay, density, defaultPage, navigationMode, refreshInterval, preloadPages, showBackToTop, codeWrap, highContrast, advisorOptionId, completionNotifications, autoScrollResults])

  useEffect(() => {
    if (!preloadPages || (!data && isMonitor)) return
    const preloadRoutes = () => Object.values(routeLoaders).forEach((load) => void load())
    if (typeof window.requestIdleCallback === "function") {
      const idleId = window.requestIdleCallback(preloadRoutes, { timeout: 1600 })
      return () => window.cancelIdleCallback(idleId)
    }
    const timeoutId = window.setTimeout(preloadRoutes, 500)
    return () => window.clearTimeout(timeoutId)
  }, [data, isMonitor, preloadPages])

  const antdThemeConfig = useMemo(() => ({
    algorithm: mode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: accent,
      colorInfo: accent,
      colorSuccess: mode === "dark" ? "#4ade80" : "#15803d",
      colorWarning: mode === "dark" ? "#fbbf24" : "#a16207",
      colorError: mode === "dark" ? "#fb7185" : "#be123c",
      colorBgLayout: mode === "dark" ? "#080d14" : "#edf2f5",
      colorText: mode === "dark" ? "#dce7ee" : "#17232d",
      borderRadius: 6,
      fontFamily: '"Segoe UI Variable", "PingFang SC", "Microsoft YaHei", sans-serif',
    },
  }), [mode, accent])

  function selectModule(id: string) {
    setSelectedModule(id)
    navigate("/modules")
  }

  function resetPreferences() {
    setMode("dark")
    setAccent("#22d3ee")
    setMotionPreference("system")
    setCodeFontSize(13)
    setTimeDisplay("local")
    setDensity("comfortable")
    setDefaultPage("/monitor")
    setNavigationMode("domains")
    setRefreshInterval(800)
    setPreloadPages(true)
    setShowBackToTop(true)
    setCodeWrap(true)
    setHighContrast(false)
    setCompletionNotifications(false)
    setAutoScrollResults(true)
  }

  function importPreferences(payload: unknown) {
    if (!payload || typeof payload !== "object") throw new Error("偏好文件必须是 JSON object")
    const envelope = payload as Record<string, unknown>
    if (envelope.product !== "FaultLattice" || envelope.schema !== 1) throw new Error("不是受支持的 FaultLattice 偏好文件")
    const preferences = envelope.preferences
    if (!preferences || typeof preferences !== "object") throw new Error("偏好文件缺少 preferences")
    const value = preferences as Record<string, unknown>
    const choices: Record<string, unknown[]> = {
      mode: ["dark", "light"],
      motionPreference: ["system", "on", "off"],
      codeFontSize: [12, 13, 14, 16],
      timeDisplay: ["local", "utc"],
      density: ["comfortable", "compact"],
      defaultPage: ["/monitor", "/experiments", "/analysis", "/integrations"],
      refreshInterval: [500, 800, 1500],
    }
    for (const [key, allowed] of Object.entries(choices)) {
      if (!allowed.includes(value[key])) throw new Error(`偏好字段 ${key} 的取值无效`)
    }
    for (const key of ["preloadPages", "showBackToTop", "codeWrap", "highContrast"]) {
      if (typeof value[key] !== "boolean") throw new Error(`偏好字段 ${key} 必须是布尔值`)
    }
    if (value.navigationMode !== undefined && value.navigationMode !== "domains" && value.navigationMode !== "pages") {
      throw new Error("偏好字段 navigationMode 的取值无效")
    }
    for (const key of ["completionNotifications", "autoScrollResults"]) {
      if (value[key] !== undefined && typeof value[key] !== "boolean") throw new Error(`偏好字段 ${key} 必须是布尔值`)
    }
    if (value.advisorOptionId !== undefined && typeof value.advisorOptionId !== "string") throw new Error("偏好字段 advisorOptionId 必须是字符串")
    if (typeof value.accent !== "string" || !/^#[0-9a-fA-F]{6}$/.test(value.accent)) throw new Error("强调色必须是六位十六进制颜色")
    setMode(value.mode as ThemeMode)
    setAccent(value.accent)
    setMotionPreference(value.motionPreference as MotionPreference)
    setCodeFontSize(value.codeFontSize as CodeFontSize)
    setTimeDisplay(value.timeDisplay as TimeDisplay)
    setDensity(value.density as Density)
    setDefaultPage(value.defaultPage as DefaultPage)
    setNavigationMode((value.navigationMode as NavigationMode | undefined) || "domains")
    setRefreshInterval(value.refreshInterval as number)
    setPreloadPages(value.preloadPages as boolean)
    setShowBackToTop(value.showBackToTop as boolean)
    setCodeWrap(value.codeWrap as boolean)
    setHighContrast(value.highContrast as boolean)
    if (typeof value.advisorOptionId === "string") setAdvisorOptionId(value.advisorOptionId)
    setCompletionNotifications(value.completionNotifications === true && "Notification" in window && Notification.permission === "granted")
    setAutoScrollResults((value.autoScrollResults as boolean | undefined) ?? true)
  }

  const connectionLabel = error ? "后端连接异常" : data ? "后端服务已连接" : isMonitor ? "正在连接后端" : "本地研发工作区"

  return (
    <ConfigProvider theme={antdThemeConfig}>
      <div className="console-shell">
        <aside className="brand-rail">
          <NavLink to={defaultPage} className="brand-link" aria-label="FaultLattice 默认首页">
            <div className="lattice-mark" aria-hidden="true">
              {Array.from({ length: 9 }, (_, index) => <span key={index} />)}
            </div>
            <div className="brand-copy"><strong>FaultLattice</strong><span>Agent Reliability Harness</span></div>
          </NavLink>
          <div className="rail-status" role="status">
            <span className={error ? "live-dot is-offline" : "live-dot"} />{connectionLabel}
          </div>
          <nav className={navigationMode === "pages" ? "main-navigation is-expanded" : "main-navigation"} aria-label="控制台主导航">
            {(navigationMode === "pages" ? pageNavigation : primaryNavigation).map((item, index) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={() => (navigationMode === "domains" && item.path === "/monitor" ? isMonitor : location.pathname === item.path) ? "nav-item active" : "nav-item"}
                onMouseEnter={() => void item.load()}
                onFocus={() => void item.load()}
              >
                {item.icon}<span>{item.label}</span><span className="nav-index">{String(index + 1).padStart(2, "0")}</span>
              </NavLink>
            ))}
          </nav>
          <div className="rail-footer">
            <span>当前工作区</span>
            <strong>本地研发项目</strong>
            <small>FaultLattice v{data?.project.version || "0.1.0"}</small>
          </div>
        </aside>

        <main className="console-main">
          <header className="topbar">
            <div className="topbar-copy" key={location.pathname}>
              <span className="section-kicker">{page.code}</span>
              <h1>{page.title}</h1>
              <p>{page.subtitle}</p>
            </div>
            <div className="refresh-area">
              <Button
                className="navigation-trigger"
                icon={<SearchOutlined />}
                onClick={() => setNavigationOpen(true)}
                aria-keyshortcuts="Control+K Meta+K"
              >
                查找功能 <kbd>Ctrl K</kbd>
              </Button>
              {lastUpdated && isMonitor && <span className="updated-at">同步于 {formatDateTime(lastUpdated.toISOString(), timeDisplay)}</span>}
              {isMonitor && (
                <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={() => void loadAll()}>
                  重新验收
                </Button>
              )}
            </div>
          </header>

          {isMonitor && navigationMode === "domains" && (
            <nav className="monitor-tabs" aria-label="监测子页面">
              <div className="monitor-tabs-scroll">
                {monitorNavigation.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    className={({ isActive }) => isActive ? "monitor-tab active" : "monitor-tab"}
                    onMouseEnter={() => void routeLoaders[item.path]()}
                    onFocus={() => void routeLoaders[item.path]()}
                  >
                    {item.icon}<span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            </nav>
          )}

          {data && isMonitorHome && (
            <div className="summary-strip">
              <div><strong>{data.summary.verified}<small>/{data.summary.modules}</small></strong><span>模块已验证</span></div>
              <div><strong>{data.summary.passed_checks}<small>/{data.summary.checks}</small></strong><span>验收项通过</span></div>
              <div><strong>{artifacts.length}</strong><span>实验运行</span></div>
              <div className="summary-note"><span className="live-dot" />数据来自当前项目与实际验收</div>
            </div>
          )}

          {isMonitor && error && <Alert className="inline-alert" type="error" showIcon title="项目状态读取失败" description={error} />}
          {isMonitor && artifactError && <Alert className="inline-alert" type="warning" showIcon title="实验产物局部不可用" description={artifactError} />}
          {isMonitor && !data && loading && <div className="initial-loading"><Spin size="large" description="正在读取项目与验收状态" /></div>}
          {isMonitor && !data && !loading && <Button icon={<ReloadOutlined />} onClick={() => void loadAll()}>重试</Button>}

          <div className="page-content" key={location.pathname}>
            <Suspense fallback={<div className="view-loading route-loading"><Spin size="large" description="正在加载页面" /></div>}>
              {isRoot ? (
                <Navigate to={defaultPage} replace />
              ) : isSettings ? (
                <SettingsView
                  mode={mode}
                  accent={accent}
                  motionPreference={motionPreference}
                  codeFontSize={codeFontSize}
                  timeDisplay={timeDisplay}
                  density={density}
                  defaultPage={defaultPage}
                  navigationMode={navigationMode}
                  refreshInterval={refreshInterval}
                  preloadPages={preloadPages}
                  showBackToTop={showBackToTop}
                  codeWrap={codeWrap}
                  highContrast={highContrast}
                  advisorOptionId={advisorOptionId}
                  completionNotifications={completionNotifications}
                  autoScrollResults={autoScrollResults}
                  projectVersion={data?.project.version || "0.1.0"}
                  onModeChange={setMode}
                  onAccentChange={setAccent}
                  onMotionChange={setMotionPreference}
                  onCodeFontSizeChange={setCodeFontSize}
                  onTimeDisplayChange={setTimeDisplay}
                  onDensityChange={setDensity}
                  onDefaultPageChange={setDefaultPage}
                  onNavigationModeChange={setNavigationMode}
                  onRefreshIntervalChange={setRefreshInterval}
                  onPreloadPagesChange={setPreloadPages}
                  onShowBackToTopChange={setShowBackToTop}
                  onCodeWrapChange={setCodeWrap}
                  onHighContrastChange={setHighContrast}
                  onAdvisorOptionChange={setAdvisorOptionId}
                  onCompletionNotificationsChange={setCompletionNotifications}
                  onAutoScrollResultsChange={setAutoScrollResults}
                  onImport={importPreferences}
                  onReset={resetPreferences}
                />
              ) : isExperiments ? (
                <ExperimentsView
                  refreshInterval={refreshInterval}
                  defaultAdvisorOptionId={advisorOptionId}
                  onAdvisorOptionChange={setAdvisorOptionId}
                  completionNotifications={completionNotifications}
                  autoScrollResults={autoScrollResults}
                />
              ) : isAnalytics ? (
                <AnalyticsView
                  defaultAdvisorOptionId={advisorOptionId}
                  onAdvisorOptionChange={setAdvisorOptionId}
                  motionEnabled={motionEnabled}
                />
              ) : isIntegrations ? (
                <ExternalAgentsView />
              ) : data ? (
                <Routes>
                  <Route path="/monitor" element={<MonitorHome data={data} artifacts={artifacts} onPreload={(path) => void routeLoaders[path]?.()} />} />
                  <Route path="/map" element={<ProjectMap data={data} onSelectModule={selectModule} />} />
                  <Route path="/modules" element={<ModulesView modules={data.modules} selectedId={selectedModule} onSelect={setSelectedModule} />} />
                  <Route path="/checks" element={<ChecksView checks={data.checks} />} />
                  <Route path="/naming" element={<NamingView />} />
                  <Route path="/artifacts" element={<ArtifactsView artifacts={artifacts} />} />
                  <Route path="*" element={<Navigate to="/monitor" replace />} />
                </Routes>
              ) : null}
            </Suspense>
          </div>
        </main>
        {showBackToTop && <BackToTop />}
      </div>
      <NavigationPalette
        open={navigationOpen}
        onClose={() => setNavigationOpen(false)}
        onNavigate={(path) => navigate(path)}
      />
    </ConfigProvider>
  )
}
