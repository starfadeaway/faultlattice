"""smolagents M3 CLI 纵向切片：真实宿主循环、模型协议与四件套复算。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("smolagents")

from faultlattice import cli  # noqa: E402
from faultlattice.adapters.smolagents import SmolagentsHost  # noqa: E402
from faultlattice.model import ModelResponse  # noqa: E402
from faultlattice.report import verify_report  # noqa: E402
from faultlattice.runner import execute_run, load_task  # noqa: E402

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class FakeProvider:
    model_id = "fake-smolagents-e2e"
    sampling_params = {"temperature": 0.0}

    def __init__(self) -> None:
        self.messages: list[list[dict]] = []

    def generate(self, messages, *, tools) -> ModelResponse:
        self.messages.append(messages)
        assert {tool["function"]["name"] for tool in tools} == {"write_file", "final_answer"}
        if len(self.messages) == 1:
            return ModelResponse.model_validate({
                "content": "",
                "tool_calls": [{
                    "id": "real-prefix-smolagents-e2e",
                    "name": "write_file",
                    "args": {"path": "output/hello.txt", "content": "hello smolagents\n"},
                }],
                "reasoning_content": "真实前缀思考",
            })
        tool_message = next(
            message for message in reversed(messages) if message["role"] == "tool"
        )
        assert "simulated tool failure after write" in tool_message["content"]
        return ModelResponse.model_validate({
            "content": "",
            "tool_calls": [{
                "id": "real-final-smolagents-e2e",
                "name": "final_answer",
                "args": {"answer": "文件已写入，但工具返回错误。"},
            }],
            "reasoning_content": "续跑思考",
        })


def test_smolagents_m3_run_and_verify_both_layers(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    source_dir = runs_root / "source-m0"
    m3_file = tmp_path / "smolagents-m3.yaml"
    raw = (REPO_ROOT / "tasks" / "smolagents_m3.yaml").read_text(encoding="utf-8")
    raw = raw.replace("runs/20261125T130640-7ce35788", str(source_dir).replace("\\", "/"))
    raw = raw.replace("model_id: kimi-k2.5", "model_id: fake-smolagents-e2e")
    # 源实验与 M3 结果出现前，先冻结任务、目标和判定声明。
    m3_file.write_text(raw, encoding="utf-8")

    source_task = load_task(REPO_ROOT / "tasks" / "smolagents_write.yaml")
    execute_run(
        source_task,
        SmolagentsHost(),
        runs_root=runs_root,
        repo_root=REPO_ROOT,
        run_id="source-m0",
    )

    original_model_factory = cli._model_for
    provider = FakeProvider()
    cli._model_for = lambda _task: provider
    try:
        result = runner.invoke(cli.app, ["run", str(m3_file), "--runs-root", str(runs_root)])
    finally:
        cli._model_for = original_model_factory
    assert result.exit_code == 0, result.output
    m3_dir = next(path for path in runs_root.iterdir() if path.name != "source-m0")
    for name in ("run.json", "steps.jsonl", "oracle.jsonl", "report.md"):
        assert (m3_dir / name).is_file()
    manifest = json.loads((m3_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["task"]["host"] == "smolagents"
    assert manifest["task"]["mode"] == "M3"
    assert manifest["model_invoked"] is True
    assert manifest["observation_status"] == "reached"
    assert manifest["versions"]["model_id"] == "fake-smolagents-e2e"
    assert manifest["versions"]["host_package_version"] == "1.26.0"
    steps = [
        json.loads(line)
        for line in (m3_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outputs = [step for step in steps if step.get("event_type") == "model_output"]
    assert [step["m3_phase"] for step in outputs] == ["prefix", "continuation"]
    assert outputs[0]["reasoning_content"] == "真实前缀思考"
    assert all(step["preset"] is False for step in outputs)
    assert all(step.get("content") != "已写入 output/hello.txt。" for step in steps)
    assert verify_report(m3_dir) == []
