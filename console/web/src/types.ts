export type CheckStatus = "passed" | "failed"
export type ModuleStatus = "verified" | "developing"
export type ReasoningMode = "default" | "enabled" | "disabled"

export interface CheckResult {
  id: string
  name: string
  command: string
  status: CheckStatus
  returncode: number
  duration_ms: number
  output: string
}

export interface ProjectModule {
  id: string
  name: string
  source_paths: string[]
  test_paths: string[]
  source_files: string[]
  dependencies: string[]
  required_checks: string[]
  checks: CheckResult[]
  paths_exist: boolean
  status: ModuleStatus
}

export interface ProjectSnapshot {
  project: {
    name: string
    subtitle: string
    version: string
    manifest: string
  }
  summary: {
    modules: number
    verified: number
    checks: number
    passed_checks: number
  }
  checks: CheckResult[]
  modules: ProjectModule[]
}

export interface Artifact {
  run_id: string
  path: string
  files: string[]
  complete: boolean
  task_id: string | null
  description: string | null
  expected_behavior: string | null
  host: string | null
  mode: string | null
  created_at: string | null
  execution_status: "completed" | "harness_failed"
  error: string | null
}

export interface PublicReport {
  path: string
  title: string
  date: string
  host: string
  summary: string
}

export interface ModelOption {
  id: string
  label: string
  model_id: string
  base_url: string | null
  capabilities: string[]
  reasoning_mode: ReasoningMode
}

export interface ExperimentTaskDetail {
  path: string
  task_id: string
  description: string
  host: string
  mode: string
  fault: Record<string, unknown> | null
  target_layers: string[]
  expected_postcondition: Record<string, unknown>
  expected_behavior: string
  min_evaluable: number
  model: {
    provider: string
    model_id: string
    sampling_params: Record<string, unknown>
    reasoning_mode: ReasoningMode
    state_claim_protocol?: "directive_failure_v1" | "independent_judgment_v1"
  } | null
}

export interface ExperimentSuite {
  id: string
  name: string
  version: number
  description: string
  tasks: string[]
  task_details: ExperimentTaskDetail[]
  requires_model: boolean
  model_configured: boolean
  advisor_configured: boolean
  advisor_model_id: string | null
}

export interface SuiteTaskResult {
  task_id: string
  task_path: string
  host: string
  mode: string
  state_claim_protocol?: "directive_failure_v1" | "independent_judgment_v1" | null
  status: "pending" | "running" | "completed" | "failed"
  run_id: string | null
  error: string | null
  events: Array<Record<string, unknown>>
  judgements: Array<Record<string, unknown>>
  advice?: string | null
  advice_model?: string | null
  advice_option_id?: string | null
  advice_generated_at?: string | null
}

export interface AdviceResult {
  task_id: string
  content: string
  advice: string
  advice_model: string
  advice_option_id: string | null
  advice_generated_at: string
}

export interface AnalysisResult {
  content: string
  model_id: string
  model_option_id: string | null
  generated_at: string
}

export interface ExternalAgentTask {
  path: string
  task_id: string
  origin: "builtin" | "custom"
  description: string
  expected_behavior: string
  mode: string
  target_layers: string[]
  fault: Record<string, unknown> | null
}

export interface ExternalAgent {
  id: string
  name: string
  entrypoint: string
  class_name: string
  created_at: string
  status: "registered" | "ready" | "error"
  error: string | null
  host_name: string | null
  host_package_version: string | null
  host_commit: string | null
  source_sha256: string | null
  capabilities: {
    modes: string[]
    injection_points: string[]
    tools: string[]
  } | null
  compatible_tasks: ExternalAgentTask[]
}

export interface SuiteRun {
  batch_id: string
  source_kind?: "builtin" | "external_agent"
  external_agent?: {
    id: string
    name: string
    entrypoint: string
    class_name: string
    source_sha256: string
    host_name: string
    host_package_version: string | null
    host_commit: string | null
  } | null
  suite_id: string
  suite_name: string
  suite_version: number
  model_option_id?: string | null
  model_id?: string | null
  model_label?: string | null
  model_reasoning_mode?: ReasoningMode | null
  model_sampling_params?: Record<string, unknown> | null
  status: "running" | "completed" | "failed"
  started_at: string
  finished_at: string | null
  current_task_id: string | null
  completed_tasks: number
  total_tasks: number
  error: string | null
  tasks: SuiteTaskResult[]
}


export type TaskFaultKind = "none" | "tool_args" | "tool_result_error" | "tool_result_empty" | "tool_result_exception"

export interface TaskDraft {
  task_id: string
  description: string
  tool_name: string
  arguments: Record<string, unknown>
  path_argument: string
  file_path: string
  content_contains: string
  final_answer: string
  expected_behavior: string
  fault_kind: TaskFaultKind
}

export interface CustomTask {
  path: string
  task_id?: string
  description?: string
  expected_behavior?: string
  mode?: string
  target_layers?: string[]
  expected_postcondition?: Record<string, unknown>
  script?: Array<Record<string, unknown>>
  oracle?: Record<string, unknown>
  min_evaluable?: number
  inconclusive_threshold?: number
  fault?: Record<string, unknown> | null
  tools?: string[]
  error?: string
}

export interface TaskPackResult {
  created: string[]
  skipped: string[]
  total_compatible: number
}

export interface AdapterDraftResult {
  content: string
  class_name: string
  warnings: string[]
  files: Array<{ path: string; characters: number; truncated: boolean }>
  input_characters: number
  estimated_input_tokens: number
  model_option_id: string
  model_id: string
  notice: string
}

export interface SaveAdapterDraftResult {
  entrypoint: string
  class_name: string
  warnings: string[]
  message: string
}

export type ParameterDifferenceType =
  | "exact_match"
  | "missing_trailing_newline"
  | "literal_backslash_n"
  | "extra_quotes_and_literal_backslash_n"
  | "native_tool_shape_error"
  | "request_error"
  | "other_argument_mismatch"

export interface ParameterToolCall {
  name: string
  args: Record<string, unknown>
}

export interface ParameterDiffRecord {
  id: string
  source_path: string
  source_commit: string
  model_id: string
  sampling_params: Record<string, unknown>
  stage_id: string
  design: string
  coordinate: string
  condition_id: string
  condition_purpose: string
  repetition: number
  request_status: "completed" | "request_error"
  classification: ParameterDifferenceType
  difference_type: ParameterDifferenceType
  prompt_sha256: string
  finish_reason: string | null
  expected_tool_call: ParameterToolCall
  actual_tool_calls: ParameterToolCall[]
  changed_fields: string[]
}

export interface ParameterDiffDataset {
  path: string
  sha256: string
  source_commit: string
  model_id: string
  sampling_params: Record<string, unknown>
  records: number
}

export interface ParameterDiffResponse {
  datasets: ParameterDiffDataset[]
  records: ParameterDiffRecord[]
  warnings: string[]
}
