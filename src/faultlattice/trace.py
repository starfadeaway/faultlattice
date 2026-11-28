"""轨迹与产物写入：run.json / steps.jsonl / oracle.jsonl。

落盘规则（spec 第 7 节）：
- 所有内容先 model_dump(mode="json")，再按 canonical JSON 编码；
- run.json 用原子写入（同目录临时文件 → 关闭 → os.replace）；
- JSONL 以二进制追加方式逐行写入，每行是一个 canonical JSON + 恰好一个 LF。
  JSONL 是只增不改的事件流，逐行追加本身就满足"已写入行不被改写"，
  因此不需要整文件重写式的原子替换。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from faultlattice.canonical import atomic_write, canonical_dumps

RUN_JSON = "run.json"
STEPS_JSONL = "steps.jsonl"
ORACLE_JSONL = "oracle.jsonl"
REPORT_MD = "report.md"


class TraceWriter:
    """单个 run 目录的产物写入器。"""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def write_run_json(self, manifest: BaseModel) -> None:
        atomic_write(self.run_dir / RUN_JSON, _dump_bytes(manifest))

    def append_step(self, event: BaseModel) -> None:
        self._append_jsonl(self.run_dir / STEPS_JSONL, event.model_dump(mode="json"))

    def append_step_dict(self, record: dict) -> None:
        """按事件判别联合校验；kind 只是适配器内部标签，不重复写入。"""
        from pydantic import TypeAdapter, ValidationError

        from faultlattice.errors import TraceFormatError
        from faultlattice.schemas import StepEvent

        payload = {key: value for key, value in record.items() if key != "kind"}
        try:
            event = TypeAdapter(StepEvent).validate_python(payload)
        except ValidationError as exc:
            raise TraceFormatError(f"steps.jsonl 事件不符合 Schema: {exc}") from exc
        self._append_jsonl(self.run_dir / STEPS_JSONL, event.model_dump(mode="json"))

    def append_oracle(self, judgement: BaseModel) -> None:
        self._append_jsonl(self.run_dir / ORACLE_JSONL, judgement.model_dump(mode="json"))

    def write_report(self, markdown: str) -> None:
        # Markdown 同样以 LF 结尾，二进制写入避免 Windows 自动 CRLF
        if not markdown.endswith("\n"):
            markdown += "\n"
        atomic_write(self.run_dir / REPORT_MD, markdown.encode("utf-8"))

    @staticmethod
    def _append_jsonl(path: Path, record: dict) -> None:
        line = canonical_dumps(record).encode("utf-8") + b"\n"
        with open(path, "ab") as fh:
            fh.write(line)


def _dump_bytes(model: BaseModel) -> bytes:
    from faultlattice.canonical import canonical_bytes

    return canonical_bytes(model.model_dump(mode="json"))


def read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL 文件为 dict 列表；空文件返回空列表。"""
    import json

    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path, "rb") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                from faultlattice.errors import TraceFormatError

                raise TraceFormatError(f"{path} 第 {lineno} 行不是合法 JSON: {exc}") from exc
    return records
