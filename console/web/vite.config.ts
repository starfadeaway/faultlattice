import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"
import { inspectAttr } from "kimi-plugin-inspect-react"

export default defineConfig(({ mode }) => {
  // 前后端共用项目根目录 .env；显式文件配置优先于旧预览进程遗留的端口变量。
  const env = loadEnv(mode, path.resolve(__dirname, "../.."), "")
  const apiPort = env.FAULTLATTICE_SERVER_PORT || process.env.FAULTLATTICE_SERVER_PORT || "8001"
  return {
    base: "./",
    plugins: [inspectAttr(), react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      // 端口被旧预览占用时明确失败，不静默跳到另一个难以排查的端口。
      strictPort: true,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: false,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            "react-vendor": ["react", "react-dom"],
            "antd-core": ["antd"],
            "antd-icons": ["@ant-design/icons"],
            markdown: ["react-markdown", "remark-gfm"],
          },
        },
      },
    },
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
  }
})
