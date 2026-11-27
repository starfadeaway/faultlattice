import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const root = fileURLToPath(new URL("../", import.meta.url))
const script = path.join(root, "scripts", "dev_preview.py")
const localPython = process.platform === "win32"
  ? path.join(root, ".venv", "Scripts", "python.exe")
  : path.join(root, ".venv", "bin", "python")
const python = process.env.FAULTLATTICE_PYTHON || (existsSync(localPython)
  ? localPython
  : process.platform === "win32" ? "python" : "python3")

const child = spawn(python, [script, ...process.argv.slice(2)], {
  cwd: root,
  env: process.env,
  stdio: "inherit",
})

child.on("error", (error) => {
  console.error(`[错误] 无法启动项目 Python：${error.message}`)
  console.error("请确认 .venv 存在，或通过 FAULTLATTICE_PYTHON 指定 Python 解释器。")
  process.exitCode = 1
})

child.on("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0)
})

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (child.exitCode === null && child.signalCode === null) child.kill(signal)
  })
}
