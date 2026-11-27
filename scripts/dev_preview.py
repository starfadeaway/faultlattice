"""Kimi Work 预览入口：把 npm 的 --port 映射给 Vite，并复用 run_all。

--host 参数被接受但保持 127.0.0.1，遵守项目不对外开放本地服务的约束。
若开发后端已经运行，则只启动前端，避免预览重开时误报 8001 端口占用。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

# 直接执行 scripts/ 内脚本时，Python 默认只把 scripts/ 放进导入路径。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_all import ROOT, load_env, main  # noqa: E402

ENV_FILE = ROOT / ".env"


def server_is_ready(port: int) -> bool:
    """只复用确认属于 FaultLattice 的健康后端，不复用占用端口的陌生服务。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and payload == {"status": "ok", "project": "FaultLattice"}
    except (OSError, ValueError):
        return False


def preview_args(
    argv: list[str] | None = None,
    *,
    server_ready: Callable[[int], bool] = server_is_ready,
) -> list[str]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--host", default="127.0.0.1")
    args, _ = parser.parse_known_args(argv)
    # 预览可能继承旧进程端口；项目文件是当前工作区的显式配置，应优先。
    file_env: dict[str, str] = {}
    load_env(ENV_FILE, file_env)
    server_port = int(
        file_env.get("FAULTLATTICE_SERVER_PORT")
        or os.environ.get("FAULTLATTICE_SERVER_PORT", "8001")
    )
    forwarded = ["--client-port", str(args.port), "--port", str(server_port)]
    if server_ready(server_port):
        return ["--only", "client", *forwarded]
    return forwarded


if __name__ == "__main__":
    raise SystemExit(main(preview_args()))
