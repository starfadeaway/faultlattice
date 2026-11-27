const tones = ["cyan", "blue", "green", "amber", "rose", "violet", "orange", "teal", "pink", "indigo", "lime"]

// 已登记模块使用固定且互不相同的颜色；新增模块使用稳定散列，不随刷新跳动。
const registeredTones: Record<string, string> = {
  core: "cyan",
  cli: "amber",
  console: "violet",
  smolagents: "rose",
  langgraph: "green",
  "m3-protocol": "blue",
  "no-upstream": "teal",
}

export function toneFor(id: string): string {
  if (registeredTones[id]) return registeredTones[id]
  const hash = Array.from(id).reduce((total, character) => (
    (total * 33 + character.codePointAt(0)!) >>> 0
  ), 5381)
  return tones[hash % tones.length]
}
