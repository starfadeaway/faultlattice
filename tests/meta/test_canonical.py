"""canonical JSON 与原子写入的跨平台测试（spec 第 7 节）。

CI 在 ubuntu 与 windows 双平台跑这些用例，防止换行 / 编码 /
序列化差异导致 verify 跨平台复算失败。
"""

import math
from pathlib import Path

import pytest

from faultlattice.canonical import (
    atomic_write,
    canonical_bytes,
    canonical_dumps,
    canonical_hash,
    sha256_hex,
)
from faultlattice.errors import ArtifactError


def test_key_sorting() -> None:
    assert canonical_dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_utf8_no_ascii_escape() -> None:
    # ensure_ascii=False：非 ASCII 字符直接保留
    assert canonical_dumps({"键": "值"}) == '{"键":"值"}'


def test_separators_no_whitespace() -> None:
    assert canonical_dumps({"a": [1, 2], "b": {"c": 3}}) == '{"a":[1,2],"b":{"c":3}}'


def test_file_ends_with_single_lf() -> None:
    data = canonical_bytes({"a": 1})
    assert data == b'{"a":1}\n'
    assert b"\r" not in data


def test_cr_is_escaped_not_literal() -> None:
    # json.dumps 会把控制字符转义，canonical JSON 文本中不会出现字面 CR
    assert canonical_dumps({"a": "x\ry"}) == '{"a":"x\\ry"}'


def test_nan_and_infinity_rejected() -> None:
    with pytest.raises(ArtifactError):
        canonical_dumps({"x": math.nan})
    with pytest.raises(ArtifactError):
        canonical_dumps({"x": math.inf})


def test_hash_is_stable_and_excludes_trailing_lf() -> None:
    obj = {"b": [1, 2], "a": "文本"}
    expected = sha256_hex('{"a":"文本","b":[1,2]}'.encode())
    assert canonical_hash(obj) == expected
    # 同一对象哈希恒定（跨进程 / 跨平台复算的基础）
    assert canonical_hash(obj) == canonical_hash(obj)


def test_atomic_write_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "run.json"
    atomic_write(target, canonical_bytes({"a": 1}))
    assert target.read_bytes() == b'{"a":1}\n'
    # 覆盖写也原子完成，且不留下临时文件
    atomic_write(target, canonical_bytes({"a": 2}))
    assert target.read_bytes() == b'{"a":2}\n'
    leftovers = list(target.parent.glob("*.tmp"))
    assert leftovers == []


def test_atomic_write_uses_lf_on_windows_too(tmp_path: Path) -> None:
    # 二进制写入，Windows 不会自动转换成 CRLF
    target = tmp_path / "x.json"
    atomic_write(target, canonical_bytes({"k": "v"}))
    assert b"\r\n" not in target.read_bytes()
