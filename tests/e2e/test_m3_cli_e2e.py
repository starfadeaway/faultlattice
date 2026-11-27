"""M3 CLI 纵向切片：源轨迹恢复、模型协议、双层 Oracle、复算与事件记录。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("langgraph")

from faultlattice import cli  # noqa: E402
from faultlattice.adapters.langgraph import LanggraphHost  # noqa: E402
from faultlattice.model import ModelResponse  # noqa: E402
from faultlattice.report import verify_report  # noqa: E402
from faultlattice.runner import execute_run, load_task  # noqa: E402

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class FakeProvider:
    model_id = "fake-e2e-model"
    sampling_params = {"temperature": 0.0}

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, messages, *, tools) -> ModelResponse:
        del messages, tools
        self.calls += 1
        if self.calls == 1:
            return ModelResponse.model_validate(
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "real-prefix-e2e",
                            "name": "write_file",
                            "args": {"path": "output/hello.txt", "content": "hello langgraph\n"},
                        }
                    ],
                    "reasoning_content": "真实前缀思考",
                }
            )
        return ModelResponse(
            content="文件已写入，但工具返回错误。", reasoning_content="续跑思考"
        )


def test_m3_run_restores_prefix_and_verifies_both_layers(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    source_dir = runs_root / "source-m0"
    m3_file = tmp_path / "m3.yaml"
    m3_path = REPO_ROOT / "tasks" / "langgraph_m3.yaml"
    m3_task = load_task(m3_path)
    assert m3_task.counterfactual_source is not None
    raw = m3_path.read_text(encoding="utf-8")
    raw = raw.replace(m3_task.counterfactual_source, str(source_dir).replace("\\", "/"))
    raw = raw.replace("model_id: kimi-k2.5", "model_id: fake-e2e-model")
    # 在源实验和 M3 结果出现前，先冻结 M3 任务声明。
    m3_file.write_text(raw, encoding="utf-8")

    source_task = load_task(REPO_ROOT / "tasks" / "langgraph_write.yaml")
    execute_run(
        source_task,
        LanggraphHost(),
        runs_root=runs_root,
        repo_root=REPO_ROOT,
        run_id="source-m0",
    )

    original_model_factory = cli._model_for
    cli._model_for = lambda _task: FakeProvider()
    try:
        result = runner.invoke(cli.app, ["run", str(m3_file), "--runs-root", str(runs_root)])
    finally:
        cli._model_for = original_model_factory
    assert result.exit_code == 0, result.output
    m3_dir = next(path for path in runs_root.iterdir() if path.name != "source-m0")
    for name in ("run.json", "steps.jsonl", "oracle.jsonl", "report.md"):
        assert (m3_dir / name).is_file()
    manifest = json.loads((m3_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["task"]["mode"] == "M3"
    assert manifest["model_invoked"] is True
    assert manifest["observation_status"] == "reached"
    assert manifest["versions"]["model_id"] == "fake-e2e-model"
    assert manifest["versions"]["sampling_params"] == {"temperature": 0.0}
    steps = [
        json.loads(line)
        for line in (m3_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    outputs = [step for step in steps if step.get("event_type") == "model_output"]
    assert [step["m3_phase"] for step in outputs] == ["prefix", "continuation"]
    assert outputs[0]["reasoning_content"] == "真实前缀思考"
    assert outputs[1]["content"] == "文件已写入，但工具返回错误。"
    assert all(step["preset"] is False for step in outputs)
    # 源 run 的预设输出只作为目标契约，不得冒充真实模型前缀或续跑结果。
    assert all(step.get("content") != "已写入 output/hello.txt。" for step in steps)
    assert verify_report(m3_dir) == []
