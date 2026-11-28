import { useCallback, useEffect, useMemo, useState } from "react"
import {
  CodeOutlined,
  DiffOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons"
import { Alert, Button, Empty, Input, Select, Spin, Tag } from "antd"
import { api } from "../api"
import { CodeViewer } from "../components/CodeViewer"
import type { ParameterDifferenceType, ParameterDiffRecord, ParameterDiffResponse } from "../types"
import { downloadMarkdown } from "../utils/downloadMarkdown"

const differenceLabels: Record<ParameterDifferenceType, string> = {
  exact_match: "精确匹配",
  missing_trailing_newline: "删除末尾换行",
  literal_backslash_n: "字面反斜杠 + n",
  extra_quotes_and_literal_backslash_n: "额外引号 + 字面换行",
  native_tool_shape_error: "工具调用形状错误",
  request_error: "请求错误",
  other_argument_mismatch: "其它参数偏差",
}

const differenceOrder: ParameterDifferenceType[] = [
  "exact_match",
  "missing_trailing_newline",
  "literal_backslash_n",
  "extra_quotes_and_literal_backslash_n",
  "other_argument_mismatch",
  "native_tool_shape_error",
  "request_error",
]

const MAX_LIST_RECORDS = 100
const MAX_VISIBLE_CHARACTERS = 4000

function valueText(value: unknown): string {
  if (typeof value === "string") return value
  if (value === undefined) return "undefined"
  return JSON.stringify(value) ?? String(value)
}

function jsonText(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? String(value)
}

function inlineValue(value: unknown): string {
  return JSON.stringify(value)?.replaceAll("|", "\\|") ?? String(value)
}

function commonAffixes(expected: string, actual: string): { prefix: number; suffix: number } {
  const left = Array.from(expected)
  const right = Array.from(actual)
  let prefix = 0
  while (prefix < left.length && prefix < right.length && left[prefix] === right[prefix]) prefix += 1
  let suffix = 0
  while (
    suffix < left.length - prefix
    && suffix < right.length - prefix
    && left[left.length - 1 - suffix] === right[right.length - 1 - suffix]
  ) suffix += 1
  return { prefix, suffix }
}

function DifferenceTag({ type }: { type: ParameterDifferenceType }) {
  return <Tag className={`difference-tag difference-${type}`}>{differenceLabels[type]}</Tag>
}

function CharacterLine({
  value,
  otherValue,
  side,
}: {
  value: unknown
  otherValue: unknown
  side: "expected" | "actual"
}) {
  const text = valueText(value)
  const other = valueText(otherValue)
  const characters = Array.from(text)
  const { prefix, suffix } = commonAffixes(text, other)
  const visible = characters.slice(0, MAX_VISIBLE_CHARACTERS)
  return (
    <code className={`character-line character-${side}`} aria-label={`${side === "expected" ? "目标" : "实际"}值：${text}`}>
      {visible.map((character, index) => {
        const changed = index >= prefix && index < characters.length - suffix
        const kind = character === "\n"
          ? "newline"
          : character === "\r"
            ? "carriage-return"
            : character === "\t"
              ? "tab"
              : character === "\\"
                ? "backslash"
                : character === '"'
                  ? "quote"
                  : "plain"
        const display = kind === "newline"
          ? "\\n"
          : kind === "carriage-return"
            ? "\\r"
            : kind === "tab"
              ? "\\t"
              : character
        const title = kind === "newline"
          ? "真实换行 · U+000A"
          : kind === "backslash"
            ? "字面反斜杠 · U+005C"
            : kind === "quote"
              ? "双引号 · U+0022"
              : `字符 ${index + 1}`
        return (
          <span
            className={`character-token character-${kind}${changed ? " is-different" : ""}`}
            key={`${index}-${character}`}
            title={title}
          >
            {display}
            {kind === "newline" && <small>LF</small>}
          </span>
        )
      })}
      {characters.length > MAX_VISIBLE_CHARACTERS && <span className="character-truncated">… 仅显示前 {MAX_VISIBLE_CHARACTERS} 个字符</span>}
    </code>
  )
}

function CharacterCompare({ field, record }: { field: string; record: ParameterDiffRecord }) {
  const actual = record.actual_tool_calls.length === 1 ? record.actual_tool_calls[0] : null
  const expectedValue = record.expected_tool_call.args[field]
  const actualValue = actual?.args[field]
  const expectedLength = Array.from(valueText(expectedValue)).length
  const actualLength = Array.from(valueText(actualValue)).length
  return (
    <div className="character-compare">
      <section>
        <h4><span>目标值 · <code>{field}</code></span><small>{expectedLength} 个字符</small></h4>
        <CharacterLine value={expectedValue} otherValue={actualValue} side="expected" />
      </section>
      <section>
        <h4><span>实际值 · <code>{field}</code></span><small>{actual ? `${actualLength} 个字符` : "无唯一调用"}</small></h4>
        {actual ? <CharacterLine value={actualValue} otherValue={expectedValue} side="actual" /> : <Empty description="没有可比较的实际参数" />}
      </section>
      <div className="character-legend" aria-label="可见字符图例">
        <span><i className="legend-newline">\n<small>LF</small></i>真实换行 U+000A</span>
        <span><i className="legend-backslash">\</i>字面反斜杠</span>
        <span><i className="legend-quote">"</i>双引号</span>
        <span><i className="legend-different">abc</i>与另一侧不同</span>
      </div>
    </div>
  )
}

function downloadParameterDiffs(
  records: ParameterDiffRecord[],
  filters: { query: string; model: string; type: string; condition: string; stage: string },
) {
  const count = (type: ParameterDifferenceType) => records.filter((record) => record.difference_type === type).length
  const lines = [
    "# FaultLattice 参数差异筛选结果",
    "",
    `生成时间：${new Date().toISOString()}`,
    `检索：${filters.query.trim() || "无"}`,
    `模型：${filters.model}`,
    `差异类型：${filters.type === "all" ? "全部" : differenceLabels[filters.type as ParameterDifferenceType]}`,
    `条件：${filters.condition}`,
    `阶段：${filters.stage}`,
    "",
    "> 本报告只整理已公开的首轮诊断证据，不执行工具、不自动修参，也不计入完整 M3 运行的 Oracle 统计。",
    "",
    "## 汇总",
    "",
    `- 当前记录：${records.length}`,
    `- 精确匹配：${count("exact_match")}`,
    `- 删除末尾换行：${count("missing_trailing_newline")}`,
    `- 字面反斜杠与 n：${count("literal_backslash_n")}`,
    `- 额外引号与字面换行：${count("extra_quotes_and_literal_backslash_n")}`,
    `- 其它参数偏差：${count("other_argument_mismatch")}`,
    "",
    "## 逐请求对比",
    "",
    "| 坐标 | 条件 | 差异 | 变化字段 | 目标 content | 实际 content |",
    "| --- | --- | --- | --- | --- | --- |",
    ...records.map((record) => {
      const actual = record.actual_tool_calls.length === 1 ? record.actual_tool_calls[0] : null
      return `| ${inlineValue(record.coordinate)} | ${inlineValue(record.condition_id)} | ${differenceLabels[record.difference_type]} | ${record.changed_fields.join(", ") || "—"} | ${inlineValue(record.expected_tool_call.args.content)} | ${inlineValue(actual?.args.content)} |`
    }),
    "",
  ]
  downloadMarkdown(`faultlattice-parameter-diffs-${new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-")}.md`, lines.join("\n"))
}

export function ParameterDiffView({ motionEnabled }: { motionEnabled: boolean }) {
  const [data, setData] = useState<ParameterDiffResponse>({ datasets: [], records: [], warnings: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const [model, setModel] = useState("all")
  const [type, setType] = useState("all")
  const [condition, setCondition] = useState("all")
  const [stage, setStage] = useState("all")
  const [selectedId, setSelectedId] = useState("")
  const [activeField, setActiveField] = useState("content")

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      setData(await api.parameterDiffs())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "参数差异证据读取失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const modelOptions = useMemo(() => [
    { value: "all", label: "全部模型" },
    ...[...new Set(data.records.map((record) => record.model_id))].sort().map((value) => ({ value, label: value })),
  ], [data.records])
  const conditionOptions = useMemo(() => [
    { value: "all", label: "全部诊断条件" },
    ...[...new Set(data.records.map((record) => record.condition_id))].sort().map((value) => ({ value, label: value })),
  ], [data.records])
  const stageOptions = useMemo(() => [
    { value: "all", label: "全部实验阶段" },
    ...[...new Set(data.records.map((record) => record.stage_id))].sort().map((value) => ({ value, label: value })),
  ], [data.records])
  const typeOptions = useMemo(() => [
    { value: "all", label: "全部差异类型" },
    ...differenceOrder
      .filter((difference) => data.records.some((record) => record.difference_type === difference))
      .map((value) => ({ value, label: `${differenceLabels[value]} · ${data.records.filter((record) => record.difference_type === value).length}` })),
  ], [data.records])

  const filteredRecords = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return data.records.filter((record) => {
      if (model !== "all" && record.model_id !== model) return false
      if (type !== "all" && record.difference_type !== type) return false
      if (condition !== "all" && record.condition_id !== condition) return false
      if (stage !== "all" && record.stage_id !== stage) return false
      if (!normalized) return true
      const actual = record.actual_tool_calls[0]
      return [
        record.coordinate,
        record.condition_id,
        record.condition_purpose,
        record.model_id,
        differenceLabels[record.difference_type],
        valueText(record.expected_tool_call.args.content),
        valueText(actual?.args.content),
      ].join(" ").toLowerCase().includes(normalized)
    })
  }, [condition, data.records, model, query, stage, type])

  const visibleRecords = filteredRecords.slice(0, MAX_LIST_RECORDS)
  const selected = visibleRecords.find((record) => record.id === selectedId) || visibleRecords[0] || null
  const selectedActual = selected?.actual_tool_calls.length === 1 ? selected.actual_tool_calls[0] : null
  const allFields = selected
    ? [...new Set([...Object.keys(selected.expected_tool_call.args), ...Object.keys(selectedActual?.args || {})])].sort()
    : []
  const currentField = selected
    ? allFields.includes(activeField)
      ? activeField
      : selected.changed_fields[0] || allFields[0]
    : ""
  const exactCount = filteredRecords.filter((record) => record.difference_type === "exact_match").length
  const missingCount = filteredRecords.filter((record) => record.difference_type === "missing_trailing_newline").length
  const encodingCount = filteredRecords.filter((record) => (
    record.difference_type === "literal_backslash_n"
    || record.difference_type === "extra_quotes_and_literal_backslash_n"
  )).length

  return (
    <div className={`view-stack parameter-diff-view ${motionEnabled ? "motion-enabled" : "motion-disabled"}`}>
      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        title="这是首轮工具参数诊断，不是 Oracle 判定"
        description="目标与实际值来自公开脱敏证据。视图不会执行工具、补齐换行或改写历史；小样本只用于定位问题，不代表稳定成功率。"
      />

      <section className="analysis-panel parameter-diff-filters" aria-label="参数差异筛选">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索坐标、条件或参数内容"
          aria-label="搜索参数差异"
        />
        <Select value={model} onChange={setModel} options={modelOptions} aria-label="筛选差异模型" />
        <Select value={condition} onChange={setCondition} options={conditionOptions} aria-label="筛选诊断条件" />
        <Select value={type} onChange={setType} options={typeOptions} aria-label="筛选参数差异类型" />
        <Select value={stage} onChange={setStage} options={stageOptions} aria-label="筛选诊断阶段" />
        <div className="parameter-filter-actions">
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新证据</Button>
          <Button
            type="primary"
            className="parameter-download"
            icon={<DownloadOutlined />}
            disabled={!filteredRecords.length}
            onClick={() => downloadParameterDiffs(filteredRecords, { query, model, type, condition, stage })}
          >下载当前 Markdown</Button>
        </div>
      </section>

      {error && <Alert type="error" showIcon title="参数差异读取失败" description={error} />}
      {data.warnings.length > 0 && <Alert type="warning" showIcon title="部分证据文件未加载" description={data.warnings.join("；")} />}

      {loading && !data.records.length ? (
        <div className="view-loading"><Spin size="large" description="正在读取并复算参数差异证据" /></div>
      ) : !data.records.length ? (
        <Empty description="尚无参数诊断证据" />
      ) : (
        <>
          <div className="analysis-metrics parameter-diff-metrics">
            <div><strong>{filteredRecords.length}</strong><span>匹配诊断请求</span><small>全部证据共 {data.records.length} 条</small></div>
            <div><strong>{exactCount}</strong><span>精确匹配</span><small>名称和完整参数对象一致</small></div>
            <div className={missingCount ? "is-risk" : ""}><strong>{missingCount}</strong><span>删除末尾换行</span><small>真实 U+000A 在末尾消失</small></div>
            <div className={encodingCount ? "is-warning" : ""}><strong>{encodingCount}</strong><span>转义或引号偏差</span><small>字面 \n 与额外引号合计</small></div>
          </div>

          {!filteredRecords.length ? <Empty description="当前筛选没有匹配记录；请调整条件" /> : (
            <div className="parameter-diff-workspace">
              <section className="analysis-panel parameter-record-panel" aria-labelledby="parameter-records-heading">
                <div className="section-heading">
                  <div><span className="section-kicker">DIAGNOSTIC REQUESTS</span><h2 id="parameter-records-heading">诊断坐标</h2></div>
                  <span>{filteredRecords.length} 条</span>
                </div>
                <div className="parameter-record-list">
                  {visibleRecords.map((record) => (
                    <button
                      type="button"
                      key={record.id}
                      className={selected?.id === record.id ? "is-selected" : ""}
                      aria-pressed={selected?.id === record.id}
                      onClick={() => { setSelectedId(record.id); setActiveField(record.changed_fields[0] || "content") }}
                    >
                      <span className="parameter-record-top"><strong>{record.coordinate}</strong><DifferenceTag type={record.difference_type} /></span>
                      <span className="parameter-record-condition">{record.condition_id}</span>
                      <code>{inlineValue(record.expected_tool_call.args.content)}</code>
                    </button>
                  ))}
                </div>
                {filteredRecords.length > MAX_LIST_RECORDS && <small className="parameter-list-limit">仅显示前 {MAX_LIST_RECORDS} 条；请缩小筛选范围。</small>}
              </section>

              {selected && (
                <section className="analysis-panel parameter-detail-panel" aria-labelledby="parameter-detail-heading">
                  <div className="section-heading parameter-detail-heading">
                    <div><span className="section-kicker">EXPECTED / ACTUAL</span><h2 id="parameter-detail-heading">参数逐字符对比</h2></div>
                    <DifferenceTag type={selected.difference_type} />
                  </div>
                  <div className="parameter-detail-meta">
                    <div><span>坐标</span><strong>{selected.coordinate}</strong></div>
                    <div><span>模型</span><strong>{selected.model_id}</strong></div>
                    <div><span>阶段</span><strong>{selected.stage_id} · 第 {selected.repetition} 次</strong></div>
                    <div><span>变化字段</span><strong>{selected.changed_fields.join("、") || "无"}</strong></div>
                  </div>
                  <p className="parameter-condition-purpose">{selected.condition_purpose || "该条件没有额外说明。"}</p>
                  {selected.difference_type !== "exact_match" && (
                    <Alert type="warning" showIcon title="严格前缀比较会拒绝这次调用" description="这里只展示差异，不会自动补换行、删除引号或把字面 \n 转成真实换行。" />
                  )}

                  <div className="parameter-field-tabs" aria-label="选择参数字段">
                    {allFields.map((field) => (
                      <Button
                        key={field}
                        size="small"
                        type={currentField === field ? "primary" : "default"}
                        aria-pressed={currentField === field}
                        onClick={() => setActiveField(field)}
                      >
                        {field}{selected.changed_fields.includes(field) ? " · 有差异" : ""}
                      </Button>
                    ))}
                  </div>

                  {currentField && <CharacterCompare field={currentField} record={selected} />}

                  {selectedActual && (
                    <details className="parameter-json-details">
                      <summary><CodeOutlined /> 查看完整 JSON 参数（带分色与格式）</summary>
                      <div className="parameter-json-grid">
                        <div><h3>目标参数</h3><CodeViewer path="target.json" content={jsonText(selected.expected_tool_call.args)} /></div>
                        <div><h3>实际参数</h3><CodeViewer path="actual.json" content={jsonText(selectedActual.args)} /></div>
                      </div>
                    </details>
                  )}

                  <div className="parameter-provenance">
                    <DiffOutlined aria-hidden="true" />
                    <div><strong>证据来源</strong><code>{selected.source_path}</code><span>提示 SHA256：<code>{selected.prompt_sha256}</code></span><span>对照提交：<code>{selected.source_commit}</code></span></div>
                  </div>
                </section>
              )}
            </div>
          )}

          <section className="analysis-panel parameter-dataset-panel" aria-label="公开证据数据集">
            <div className="section-heading"><div><span className="section-kicker">PUBLIC EVIDENCE</span><h2>数据集与复算边界</h2></div><span>{data.datasets.length} 个文件</span></div>
            {data.datasets.map((dataset) => (
              <div className="parameter-dataset-row" key={dataset.path}>
                <div><strong>{dataset.path.split("/").pop()}</strong><code>{dataset.path}</code></div>
                <div><span>{dataset.records} 条</span><span>{dataset.model_id}</span><code>SHA256 {dataset.sha256}</code></div>
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  )
}
