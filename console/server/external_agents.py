"""控制台兼容入口；登记与预检实现位于可安装核心包。"""

from faultlattice.external_registry import (
    ExternalAgentService,
    ExternalCapabilities,
    ExternalRegistration,
    ExternalRegistry,
)

__all__ = [
    "ExternalAgentService",
    "ExternalCapabilities",
    "ExternalRegistration",
    "ExternalRegistry",
]
