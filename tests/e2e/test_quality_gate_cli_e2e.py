"""质量门禁 CLI 对公开 baseline 做真实复算，并输出可审计 Markdown。"""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from faultlattice.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE = REPO_ROOT / "quality" / "public-sample.yaml"
SAMPLE = REPO_ROOT / yaml.safe_load(BASELINE.read_text(encoding="utf-8"))["runs"][0]


def test_quality_gate_public_sample_cli(tmp_path: Path) -> None:
    output = tmp_path / "quality-gate.md"
    result = CliRunner().invoke(
        app,
        [
            "quality-gate",
            str(SAMPLE),
            "--baseline",
            str(BASELINE),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "门禁通过" in result.output
    text = output.read_text(encoding="utf-8")
    assert "faultlattice-quality-gate" in text
    assert '"passed":true' in text
    assert "不替代 pytest、Ruff、Pyright" in text


EXTERNAL_BASELINE = REPO_ROOT / "quality" / "external-agent-m0.yaml"
EXTERNAL_SAMPLES = [
    REPO_ROOT / "runs" / "_sample" / run_id
    for run_id in (
        "20261127T131928-4a109d3f",
        "20261126T175052-1730a492",
        "20261127T131958-b5e13aff",
        "20261126T180523-058c206a",
        "20261127T145247-77cdae58",
        "20261127T145248-20a065b6",
    )
]


def test_external_agent_quality_gate_cli_compares_six_coordinates(tmp_path: Path) -> None:
    output = tmp_path / "external-agent-quality-gate.md"
    result = CliRunner().invoke(
        app,
        [
            "quality-gate",
            *(str(path) for path in EXTERNAL_SAMPLES),
            "--baseline",
            str(EXTERNAL_BASELINE),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "6 个完整坐标" in result.output
    text = output.read_text(encoding="utf-8")
    assert '"passed":true' in text
    assert text.count("framework=completed / framework=completed") == 2
    assert "no_fault_verdict_changed" not in text
