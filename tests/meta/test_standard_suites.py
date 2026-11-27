"""标准实验矩阵与人读报告的持续契约。"""

from pathlib import Path

from console.server.experiments import ExperimentService
from faultlattice.counterfactual import CounterfactualRunner
from faultlattice.report import render_report, verify_report
from faultlattice.runner import load_manifest, load_task

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_standard_suites_have_real_m3_sources() -> None:
    service = ExperimentService(REPO_ROOT)
    suites = {suite["id"]: suite for suite in service.suites()}
    assert len(suites["framework-m0"]["tasks"]) == 11
    assert len(suites["process-timeout"]["tasks"]) == 1
    assert len(suites["langgraph-m3"]["tasks"]) == 4

    for path in suites["langgraph-m3"]["tasks"]:
        task = load_task(REPO_ROOT / path)
        assert task.counterfactual_source is not None
        source_dir = REPO_ROOT / task.counterfactual_source
        source = load_manifest(source_dir)
        assert source.task.host == task.host
        assert source.task.fault == task.fault
        assert source.injection_applied
        assert CounterfactualRunner._prefix_before_first_injection(source_dir)


def test_run_report_is_human_readable_without_breaking_verification() -> None:
    run_dir = REPO_ROOT / "runs" / "_sample" / "20261125T071752-d22652f8"
    report = render_report(run_dir)
    assert "## 一、这次测试做了什么" in report
    assert "真实 ToolCallingAgent 执行 write_file" in report
    assert "运行时间 | 2026-11-25 07:17:52 UTC" in report
    assert "是否真实调用模型：否" in report
    assert "本次前段坐标：`smolagents × M0 × tool_fault`" in report
    assert "## 四、实际执行过程" in report
    assert "具体故障参数" in report
    assert "simulated tool failure after write" in report
    assert "### Harness 独立后置核验" in report
    assert "不依赖被测模型是否拥有读取工具" in report
    assert "### 预设最终回答（非真实模型输出）" in report
    assert "N/A（单次样本）" in report
    assert "查看机器可读原始证据" in report
    assert "逐步事件摘要" in report
    assert "预设脚本输出" in report
    assert "## 五、Oracle 如何判定" in report
    assert '"task_succeeded":true' in report
    assert "执行完成不等于没有缺陷" in report
    assert "四件套齐全不等于测试通过" in report
    assert verify_report(run_dir) == []
