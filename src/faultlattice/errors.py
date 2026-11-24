"""FaultLattice 异常分类。

分类与命名见 docs/NAMING.md 第 8 节。设计要点：

- 预期注入故障（如模拟 TimeoutError）是实验数据，不属于这里的异常，
  不得让它们把程序整体打崩；
- 这里的异常全部表示 Harness 自身出了问题（配置、adapter、轨迹、写入等），
  对应 CLI 的非零退出码；
- 抛出时尽量携带 run_id / step_id / host / fault_type 上下文，方便定位。
"""

from __future__ import annotations


class FaultLatticeError(Exception):
    """所有 Harness 自身错误的基类。"""


class ConfigurationError(FaultLatticeError):
    """配置错误：非法故障组合、预注册文件缺失字段、A/B 批次校验失败等。"""


class AdapterCapabilityError(FaultLatticeError):
    """adapter 不具备所需能力，或注入点预检失败（防假绿，必须显式报错）。"""


class InjectionError(FaultLatticeError):
    """故障注入机制自身失败（不是"注入的故障生效"）。"""


class TraceFormatError(FaultLatticeError):
    """轨迹文件格式错误：steps.jsonl / oracle.jsonl 无法解析或字段缺失。"""


class ReplayError(FaultLatticeError):
    """重放失败：状态恢复、轨迹与代码版本不一致等。"""


class OracleError(FaultLatticeError):
    """Oracle 判定器自身错误（证据不足是 inconclusive，不是异常）。"""


class ArtifactError(FaultLatticeError):
    """产物读写错误：canonical JSON 非法（NaN/Infinity）、原子写入失败等。"""
