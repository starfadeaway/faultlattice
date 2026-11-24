"""故障模型单元测试：合法组合表与 experiment_family 推导（spec 第 3 节）。"""

import pytest

from faultlattice.errors import ConfigurationError
from faultlattice.faults import LEGAL_COMBINATIONS, derive_experiment_family
from faultlattice.schemas import (
    ExperimentFamily,
    FaultSpec,
    FaultType,
    InjectionPoint,
    SurfaceAs,
)


def test_legal_combination_count_matches_spec() -> None:
    # spec 第 3 节表格共 13 种合法组合；改动表格必须先改 spec
    assert len(LEGAL_COMBINATIONS) == 13


def test_family_derived_from_injection_point() -> None:
    assert derive_experiment_family(InjectionPoint.TOOL_ARGS) is ExperimentFamily.TOOL_FAULT
    assert derive_experiment_family(InjectionPoint.TOOL_RESULT) is ExperimentFamily.TOOL_FAULT
    assert (
        derive_experiment_family(InjectionPoint.OBSERVATION)
        is ExperimentFamily.CONTEXT_CORRUPTION
    )


_SORTED_COMBINATIONS: list[tuple[InjectionPoint, FaultType, SurfaceAs]] = sorted(
    LEGAL_COMBINATIONS, key=lambda t: (t[0].value, t[1].value, t[2].value)
)


@pytest.mark.parametrize(("point", "ftype", "surface"), _SORTED_COMBINATIONS)
def test_legal_combinations_accepted(
    point: InjectionPoint, ftype: FaultType, surface: SurfaceAs
) -> None:
    spec = FaultSpec(injection_point=point, fault_type=ftype, surface_as=surface)
    assert spec.experiment_family == derive_experiment_family(point)


def test_illegal_combination_rejected() -> None:
    # observation + return_value 不存在 return / raise 语义，必须报配置错误
    with pytest.raises(ConfigurationError):
        FaultSpec(
            injection_point=InjectionPoint.OBSERVATION,
            fault_type=FaultType.TIMEOUT,
            surface_as=SurfaceAs.RETURN_VALUE,
        )


def test_tool_result_timeout_cannot_be_not_applicable() -> None:
    with pytest.raises(ConfigurationError):
        FaultSpec(
            injection_point=InjectionPoint.TOOL_RESULT,
            fault_type=FaultType.TIMEOUT,
            surface_as=SurfaceAs.NOT_APPLICABLE,
        )
