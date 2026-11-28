"""参数诊断公开证据的只读加载与独立复算。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

EVIDENCE_SCHEMA = "faultlattice.prefix-diagnostic-evidence-v1"
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_RECORDS_PER_DATASET = 5000

Classification = Literal[
    "exact_match",
    "missing_trailing_newline",
    "other_argument_mismatch",
    "native_tool_shape_error",
    "request_error",
]


class ToolCallEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    args: dict[str, Any]


class ConditionEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = Field(default=None, max_length=100_000)
    purpose: str = Field(default="", max_length=2000)


class RequestEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coordinate: str = Field(min_length=1, max_length=300)
    condition_id: str = Field(min_length=1, max_length=200)
    repetition: int = Field(ge=1)
    request_status: Literal["completed", "request_error"]
    classification: Classification
    expected_tool_call: ToolCallEvidence
    actual_tool_calls: list[ToolCallEvidence] = Field(default_factory=list, max_length=100)
    finish_reason: str | None = Field(default=None, max_length=100)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class StageEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage_id: str = Field(min_length=1, max_length=100)
    design: str = Field(default="", max_length=2000)
    conditions: dict[str, ConditionEvidence] = Field(default_factory=dict)
    requests: list[RequestEvidence] = Field(max_length=MAX_RECORDS_PER_DATASET)


class EvidenceDocument(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_name: Literal["faultlattice.prefix-diagnostic-evidence-v1"] = Field(alias="schema")
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    model_id: str = Field(min_length=1, max_length=200)
    sampling_params: dict[str, Any]
    total_requests: int = Field(ge=0, le=MAX_RECORDS_PER_DATASET)
    stages: list[StageEvidence] = Field(min_length=1)


def _classify(
    expected: ToolCallEvidence, actual_calls: list[ToolCallEvidence], request_status: str
) -> Classification:
    if request_status == "request_error":
        return "request_error"
    if len(actual_calls) != 1:
        return "native_tool_shape_error"
    actual = actual_calls[0]
    if actual == expected:
        return "exact_match"
    expected_args = expected.args
    actual_args = actual.args
    expected_content = expected_args.get("content")
    if (
        actual.name == expected.name
        and set(actual_args) == set(expected_args)
        and actual_args.get("path") == expected_args.get("path")
        and isinstance(expected_content, str)
        and expected_content.endswith("\n")
        and actual_args.get("content") == expected_content[:-1]
    ):
        return "missing_trailing_newline"
    return "other_argument_mismatch"


def _difference_type(
    classification: Classification,
    expected: ToolCallEvidence,
    actual_calls: list[ToolCallEvidence],
) -> str:
    if classification != "other_argument_mismatch":
        return classification
    actual = actual_calls[0].args
    wanted = expected.args
    expected_content = wanted.get("content")
    expected_path = wanted.get("path")
    if not isinstance(expected_content, str) or not isinstance(expected_path, str):
        return classification
    without_newline = expected_content.removesuffix("\n")
    if (
        actual.get("path") == expected_path
        and actual.get("content") == without_newline + "\\n"
        and set(actual) == set(wanted)
    ):
        return "literal_backslash_n"
    if (
        actual.get("path") == f'"{expected_path}"'
        and actual.get("content") == f'"{without_newline}\\n"'
        and set(actual) == set(wanted)
    ):
        return "extra_quotes_and_literal_backslash_n"
    return classification


def _changed_fields(expected: dict[str, Any], actual: dict[str, Any] | None) -> list[str]:
    if actual is None:
        return sorted(expected)
    return sorted(
        key
        for key in set(expected) | set(actual)
        if key not in expected or key not in actual or expected[key] != actual[key]
    )


class ParameterDiffService:
    """只扫描固定公开证据目录；损坏文件转为局部警告，不泄露绝对路径。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.evidence_root = self.root / "reports" / "external" / "evidence"

    def list(self) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        datasets: list[dict[str, Any]] = []
        warnings: list[str] = []
        if not self.evidence_root.is_dir():
            return {"datasets": [], "records": [], "warnings": warnings}
        for path in sorted(self.evidence_root.glob("*.json")):
            relative = path.relative_to(self.root).as_posix()
            try:
                if path.stat().st_size > MAX_EVIDENCE_BYTES:
                    raise ValueError("证据文件超过 8 MiB 限制")
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or raw.get("schema") != EVIDENCE_SCHEMA:
                    continue
                document = EvidenceDocument.model_validate(raw)
                dataset_records = self._records(document, relative)
                if len(dataset_records) != document.total_requests:
                    raise ValueError(
                        f"total_requests={document.total_requests}，实际为 {len(dataset_records)}"
                    )
                datasets.append({
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "source_commit": document.source_commit,
                    "model_id": document.model_id,
                    "sampling_params": document.sampling_params,
                    "records": len(dataset_records),
                })
                records.extend(dataset_records)
            except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                warnings.append(f"{path.name} 未加载：{exc}")
        return {"datasets": datasets, "records": records, "warnings": warnings}

    @staticmethod
    def _records(document: EvidenceDocument, source_path: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for stage in document.stages:
            for request in stage.requests:
                if request.coordinate in seen:
                    raise ValueError(f"重复坐标：{request.coordinate}")
                seen.add(request.coordinate)
                classification = _classify(
                    request.expected_tool_call, request.actual_tool_calls, request.request_status
                )
                if classification != request.classification:
                    raise ValueError(
                        f"{request.coordinate} 分类不一致：登记 {request.classification}，"
                        f"复算 {classification}"
                    )
                actual = request.actual_tool_calls[0] if len(request.actual_tool_calls) == 1 else None
                expected_args = request.expected_tool_call.args
                actual_args = actual.args if actual is not None else None
                output.append({
                    "id": f"{source_path}#{request.coordinate}",
                    "source_path": source_path,
                    "source_commit": document.source_commit,
                    "model_id": document.model_id,
                    "sampling_params": document.sampling_params,
                    "stage_id": stage.stage_id,
                    "design": stage.design,
                    "coordinate": request.coordinate,
                    "condition_id": request.condition_id,
                    "condition_purpose": (
                        stage.conditions.get(request.condition_id, ConditionEvidence()).purpose
                    ),
                    "repetition": request.repetition,
                    "request_status": request.request_status,
                    "classification": classification,
                    "difference_type": _difference_type(
                        classification, request.expected_tool_call, request.actual_tool_calls
                    ),
                    "prompt_sha256": request.prompt_sha256,
                    "finish_reason": request.finish_reason,
                    "expected_tool_call": request.expected_tool_call.model_dump(),
                    "actual_tool_calls": [call.model_dump() for call in request.actual_tool_calls],
                    "changed_fields": _changed_fields(expected_args, actual_args),
                })
        return output
