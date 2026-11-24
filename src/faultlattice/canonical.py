"""canonical JSON 与哈希规则、原子文件写入。

规则全文见 docs/spec-v0.1.md 第 7.1 / 7.2 节。这里集中实现，保证
run.json、steps.jsonl、oracle.jsonl 以及所有哈希输入使用同一套编码，
否则跨平台复算（faultlattice verify）会出现字节级不一致。

关键不变量：
- key 按 Unicode code point 排序（json.dumps(sort_keys=True) 的行为）；
- UTF-8、ensure_ascii=False、separators=(",", ":")，无多余空白；
- 文件末尾恰好一个 \\n；CR 不会出现在落盘内容中（json.dumps 会转义
  字符串内的控制字符，写入一律用二进制模式，Windows 不会引入 CRLF）；
- 浮点不允许 NaN / Infinity（allow_nan=False 会直接抛 ValueError，
  调用方应包装成 ArtifactError）；
- 哈希输入是"不含末尾换行"的 canonical JSON 字节。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from faultlattice.errors import ArtifactError


def canonical_dumps(obj: Any) -> str:
    """把对象编码为 canonical JSON 字符串（不含末尾换行）。

    参见 docs/spec-v0.1.md 第 7.1 节。Pydantic 模型需先
    ``model_dump(mode="json")`` 再传入，避免 datetime 等类型直接进 json。
    """
    try:
        text = json.dumps(
            obj,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        # NaN / Infinity / 不可序列化类型都属于产物错误，显式报出而不是静默降级
        raise ArtifactError(f"对象无法编码为 canonical JSON: {exc}") from exc
    return text


def canonical_bytes(obj: Any) -> bytes:
    """canonical JSON 的落盘字节形式：内容 + 恰好一个 LF。"""
    return (canonical_dumps(obj) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """对字节计算 SHA-256，返回十六进制小写。哈希输入约定见模块 docstring。"""
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj: Any) -> str:
    """对 canonical JSON（不含末尾换行）计算 SHA-256。"""
    return sha256_hex(canonical_dumps(obj).encode("utf-8"))


def atomic_write(path: Path, data: bytes) -> None:
    """原子写入：同目录临时文件 → 写入并关闭 → os.replace。

    Windows 上必须先关闭文件句柄再 os.replace，否则目标被占用时会
    PermissionError；这里用 with 保证句柄释放。tempfile 放在目标同目录，
    保证 os.replace 是同一文件系统内的原子重命名。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # 清理临时文件，避免失败后在 runs/ 里留下垃圾
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
