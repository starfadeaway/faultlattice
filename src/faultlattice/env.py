"""本机简单 KEY=VALUE 环境文件解析；已有进程环境始终优先。"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path


def load_env(path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """读取本地 .env，不覆盖调用方或服务管理器已经注入的值。"""
    environ = os.environ if environ is None else environ
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        environ.setdefault(key.strip(), value)
