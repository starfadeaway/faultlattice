export type TimeDisplay = "local" | "utc"

export function storedTimeDisplay(): TimeDisplay {
  try {
    return window.localStorage.getItem("faultlattice-time-display") === "utc" ? "utc" : "local"
  } catch {
    return "local"
  }
}

/** 将带时区的实验时间统一渲染为 YYYY-MM-DD HH:mm:ss。 */
export function formatDateTime(value: string | null | undefined, display = storedTimeDisplay()): string {
  if (!value) return "未记录时间"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "无效时间"
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: display === "utc" ? "UTC" : undefined,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || "00"
  const formatted = `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}:${part("second")}`
  return display === "utc" ? `${formatted} UTC` : formatted
}
