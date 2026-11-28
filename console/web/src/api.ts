import type { AdapterDraftResult, AdviceResult, AnalysisResult, Artifact, CustomTask, ExperimentSuite, ExternalAgent, ModelOption, ProjectSnapshot, PublicReport, SaveAdapterDraftResult, SuiteRun, TaskDraft, TaskPackResult } from "./types"

async function responseError(response: Response, fallback: string): Promise<Error> {
  try {
    const body = await response.json()
    return new Error(body.detail || fallback)
  } catch {
    return new Error(fallback)
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) throw await responseError(response, `HTTP ${response.status}`)
  return response.json() as Promise<T>
}

async function requestText(path: string, fallback: string): Promise<string> {
  const response = await fetch(path)
  if (!response.ok) throw await responseError(response, `${fallback}（HTTP ${response.status}）`)
  return response.text()
}

async function post<T>(path: string, fallback: string, body?: Record<string, unknown>): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  })
  if (!response.ok) throw await responseError(response, `${fallback}（HTTP ${response.status}）`)
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; project: string }>("/api/health"),
  project: () => request<ProjectSnapshot>("/api/project"),
  artifacts: () => request<Artifact[]>("/api/artifacts"),
  naming: () => request<{ path: string; content: string }>("/api/naming"),
  source: (path: string) =>
    request<{ path: string; content: string }>(`/api/source?path=${encodeURIComponent(path)}`),
  report: (runId: string) =>
    requestText(`/api/artifacts/${encodeURIComponent(runId)}/report`, "报告读取失败"),
  publicReports: () => request<PublicReport[]>("/api/public-reports"),
  publicReport: (path: string) =>
    requestText(`/api/public-reports/content?path=${encodeURIComponent(path)}`, "公开报告读取失败"),
  experimentSuites: () => request<ExperimentSuite[]>("/api/experiments/suites"),
  experimentModels: () => request<ModelOption[]>("/api/experiments/models"),
  experimentHistory: () => request<SuiteRun[]>("/api/experiments/history"),
  experimentDetail: (batchId: string) =>
    request<SuiteRun>(`/api/experiments/history/${encodeURIComponent(batchId)}`),
  runSuite: (suiteId: string, modelOptionId?: string) =>
    post<SuiteRun>("/api/experiments/run", "套件启动失败", {
      suite_id: suiteId,
      model_option_id: modelOptionId || null,
    }),
  suiteReport: (batchId: string) =>
    requestText(`/api/experiments/history/${encodeURIComponent(batchId)}/report`, "套件报告读取失败"),
  generateAnalysis: (
    selections: Array<{ batch_id: string; task_id: string }>,
    layer: string,
    modelOptionId: string,
  ) =>
    post<AnalysisResult>("/api/experiments/analysis", "LLM 实验分析生成失败", {
      selections,
      layer,
      model_option_id: modelOptionId || null,
    }),
  generateAdvice: (batchId: string, taskId: string, advisorOptionId: string) =>
    post<AdviceResult>(
      `/api/experiments/history/${encodeURIComponent(batchId)}/tasks/${encodeURIComponent(taskId)}/advice`,
      "LLM 修改建议生成失败",
      { advisor_option_id: advisorOptionId },
    ),
  externalAgents: () => request<ExternalAgent[]>("/api/external-agents"),
  registerExternalAgent: (body: { agent_id: string; name: string; entrypoint: string; class_name: string }) =>
    post<ExternalAgent>("/api/external-agents/register", "外部 Agent 登记失败", body),
  preflightExternalAgent: (agentId: string) =>
    post<ExternalAgent>(`/api/external-agents/${encodeURIComponent(agentId)}/preflight`, "外部 Agent 预检失败"),
  runExternalAgent: (agentId: string, taskPath: string, modelOptionId?: string) =>
    post<SuiteRun>(`/api/external-agents/${encodeURIComponent(agentId)}/run`, "外部 Agent 测试启动失败", {
      task_path: taskPath,
      model_option_id: modelOptionId || null,
    }),
  customTasks: () => request<CustomTask[]>("/api/task-authoring"),
  createCustomTask: (agentId: string, draft: TaskDraft) =>
    post<{ path: string; task: Record<string, unknown> }>("/api/task-authoring", "自定义任务保存失败", {
      agent_id: agentId,
      draft: draft as unknown as Record<string, unknown>,
    }),
  deleteCustomTask: async (taskId: string) => {
    const response = await fetch(`/api/task-authoring/${encodeURIComponent(taskId)}`, { method: "DELETE" })
    if (!response.ok) throw await responseError(response, "自定义任务删除失败")
    return response.json() as Promise<{ deleted: boolean }>
  },
  createTaskPack: (agentId: string) =>
    post<TaskPackResult>("/api/task-authoring/pack", "标准任务包生成失败", { agent_id: agentId }),
  importTaskFile: (filename: string, content: string) =>
    post<{ draft: TaskDraft; notice: string }>("/api/task-authoring/import", "任务文件导入失败", { filename, content }),
  generateTaskDraft: (agentId: string, goal: string, modelOptionId: string) =>
    post<{ draft: TaskDraft; model_option_id: string; model_id: string; notice: string }>("/api/task-authoring/ai-draft", "AI 任务草案生成失败", {
      agent_id: agentId,
      goal,
      model_option_id: modelOptionId || null,
    }),
  uploadAdapterSource: (filename: string, content: string) =>
    post<{ path: string; filename: string; characters: number; notice: string }>("/api/adapter-authoring/upload", "资料文件上传失败", { filename, content }),
  generateAdapterDraft: (sourcePaths: string[], agentGoal: string, modelOptionId: string) =>
    post<AdapterDraftResult>("/api/adapter-authoring/draft", "AI 适配器草案生成失败", {
      source_paths: sourcePaths,
      agent_goal: agentGoal,
      model_option_id: modelOptionId || null,
    }),
  saveAdapterDraft: (agentId: string, className: string, content: string, allowReviewedRisks = false) =>
    post<SaveAdapterDraftResult>("/api/adapter-authoring/save", "适配器草案保存失败", {
      agent_id: agentId,
      class_name: className,
      content,
      allow_reviewed_risks: allowReviewedRisks,
    }),
}
