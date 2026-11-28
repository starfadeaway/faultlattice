"""用当前代码现场生成确定性 current，再与版本化公开 baseline 比较。"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from faultlattice.adapters.local import LocalControlledHost
from faultlattice.quality import (
    QualityGateResult,
    evaluate_quality_gate,
    generate_quality_gate_report,
    load_quality_baseline,
)
from faultlattice.report import generate_report
from faultlattice.runner import execute_run, load_task


def run_public_regression(
    *, repo_root: Path, baseline_path: Path, output_path: Path
) -> QualityGateResult:
    """current 位于临时目录，绝不复用 baseline 或读取本机私有运行。"""
    root = Path(repo_root).resolve()
    baseline_file = Path(baseline_path)
    if not baseline_file.is_absolute():
        baseline_file = root / baseline_file
    baseline_name, baseline_dirs = load_quality_baseline(baseline_file, root)
    with tempfile.TemporaryDirectory(prefix="faultlattice-public-current-") as temporary:
        current = execute_run(
            load_task(root / "tasks" / "local_write.yaml"),
            LocalControlledHost(),
            runs_root=Path(temporary) / "runs",
            repo_root=root,
        )
        generate_report(current)
        result = evaluate_quality_gate(baseline_name, baseline_dirs, [current])
    generate_quality_gate_report(result, output_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path("quality/public-sample.yaml"))
    parser.add_argument("--output", type=Path, default=Path("reports/quality-gate.md"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output if args.output.is_absolute() else root / args.output
    result = run_public_regression(
        repo_root=root, baseline_path=args.baseline, output_path=output
    )
    if not result.passed:
        for violation in result.violations:
            print(f"回归拒绝 [{violation.code}]: {violation.message}")
        return 1
    print(
        f"门禁通过：现场生成 current，配对 {result.matched_coordinates} 个完整坐标；"
        f"报告已写入 {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
