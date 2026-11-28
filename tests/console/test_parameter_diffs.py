"""参数差异证据：独立复算、局部损坏与真实公开 API。"""

import json
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from console.server.app import app
from console.server.diagnostics import ParameterDiffService

COMMIT = "5c9fdedd85f192b842765242e6aa89df584f3942"
PROMPT_HASH = "a" * 64


def _request(
    coordinate: str,
    expected_content: str,
    actual_content: str,
    classification: str,
    *,
    actual_path: str = "output/hello.txt",
) -> dict:
    return {
        "coordinate": coordinate,
        "condition_id": "condition",
        "repetition": int(coordinate.rsplit("-", 1)[-1]),
        "request_status": "completed",
        "classification": classification,
        "expected_tool_call": {
            "name": "write_file",
            "args": {"path": "output/hello.txt", "content": expected_content},
        },
        "actual_tool_calls": [{
            "name": "write_file",
            "args": {"path": actual_path, "content": actual_content},
        }],
        "finish_reason": "tool_calls",
        "prompt_sha256": PROMPT_HASH,
    }


def _write_evidence(root: Path, name: str, requests: list[dict]) -> None:
    path = root / "reports" / "external" / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "faultlattice.prefix-diagnostic-evidence-v1",
        "source_commit": COMMIT,
        "model_id": "MiniMax-M3.1-Flash",
        "sampling_params": {"temperature": 0.0},
        "total_requests": len(requests),
        "stages": [{
            "stage_id": "test",
            "design": "可控证据加载测试",
            "conditions": {"condition": {"purpose": "测试可见字符差异"}},
            "requests": requests,
        }],
    }, ensure_ascii=False), encoding="utf-8")


def test_parameter_diff_service_recomputes_visible_difference_types(tmp_path: Path) -> None:
    _write_evidence(tmp_path, "valid.json", [
        _request("exact-1", "hello", "hello", "exact_match"),
        _request("missing-2", "hello\n", "hello", "missing_trailing_newline"),
        _request("literal-3", "hello\n", "hello\\n", "other_argument_mismatch"),
        _request(
            "quotes-4", "hello\n", '"hello\\n"', "other_argument_mismatch",
            actual_path='"output/hello.txt"',
        ),
    ])

    result = ParameterDiffService(tmp_path).list()

    assert result["warnings"] == []
    assert [r["difference_type"] for r in result["records"]] == [
        "exact_match",
        "missing_trailing_newline",
        "literal_backslash_n",
        "extra_quotes_and_literal_backslash_n",
    ]
    assert result["records"][1]["changed_fields"] == ["content"]
    assert result["records"][3]["changed_fields"] == ["content", "path"]
    assert result["datasets"][0]["records"] == 4


def test_parameter_diff_service_keeps_valid_dataset_when_another_is_invalid(
    tmp_path: Path,
) -> None:
    _write_evidence(tmp_path, "valid.json", [
        _request("exact-1", "hello", "hello", "exact_match"),
    ])
    _write_evidence(tmp_path, "invalid.json", [
        _request("wrong-1", "hello\n", "hello", "exact_match"),
    ])
    ignored = tmp_path / "reports" / "external" / "evidence" / "other.json"
    ignored.write_text(json.dumps({"schema": "other-evidence"}), encoding="utf-8")

    result = ParameterDiffService(tmp_path).list()

    assert len(result["records"]) == 1
    assert result["records"][0]["coordinate"] == "exact-1"
    assert len(result["datasets"]) == 1
    assert len(result["warnings"]) == 1
    assert "invalid.json" in result["warnings"][0]
    assert "复算 missing_trailing_newline" in result["warnings"][0]


def test_parameter_diff_api_reads_all_public_diagnostic_requests() -> None:
    response = TestClient(app).get("/api/analysis/parameter-diffs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["warnings"] == []
    assert len(payload["records"]) == 24
    assert payload["datasets"][0]["records"] == 24
    counts = Counter(record["difference_type"] for record in payload["records"])
    assert counts == {
        "exact_match": 17,
        "missing_trailing_newline": 4,
        "literal_backslash_n": 2,
        "extra_quotes_and_literal_backslash_n": 1,
    }
    assert all(record["model_id"] == "MiniMax-M3.1-Flash" for record in payload["records"])
