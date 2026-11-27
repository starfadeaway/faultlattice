"""同步工具的跨平台进程隔离与真实硬终止。

只有显式声明 ``timeout_mode=process`` 的本地受控任务使用本模块。子进程
由 ``spawn`` 创建，避免 Windows 与 POSIX 的默认启动方式不同；超时后先
terminate，必要时 kill，并等待进程回收。线程超时不能终止阻塞中的同步函数，
因此不得用 ``asyncio.to_thread + wait_for`` 替代这里的进程边界。

该边界只保证终止当前 worker 进程，不承诺清理 worker 自行创建的任意后代
进程；需要运行不可信代码时还应使用操作系统沙箱，而不是把本模块当作安全边界。
"""

from __future__ import annotations

import math
import multiprocessing
import queue
import time
from collections.abc import Callable
from multiprocessing.process import BaseProcess
from typing import Any

from faultlattice.errors import ConfigurationError, InjectionError


class ProcessTimeoutError(TimeoutError):
    """真实进程超时；它是 TimeoutError，同时携带可审计的终止证据。"""

    def __init__(self, message: str, *, worker_pid: int, elapsed_seconds: float) -> None:
        super().__init__(message)
        self.worker_pid = worker_pid
        self.elapsed_seconds = elapsed_seconds
        self.process_terminated = True


def _worker_entry(
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    output: Any,
) -> None:
    """子进程只通过 JSON 可序列化结果通信；内部异常不是预注册故障。"""
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        output.put({"status": "error", "error_type": type(exc).__name__, "message": str(exc)})
    else:
        output.put({"status": "ok", "result": result})


def _stop_worker(process: BaseProcess) -> None:
    """终止并回收 worker；操作系统拒绝终止时必须报告 Harness 错误。"""
    if process.is_alive():
        process.terminate()
        process.join(timeout=2)
    if process.is_alive():
        process.kill()
        process.join(timeout=2)
    if process.is_alive():
        raise InjectionError(f"工具子进程 {process.pid} 在 terminate/kill 后仍未退出")


def run_with_process_timeout(
    function: Callable[..., Any],
    *args: Any,
    timeout_seconds: float,
    **kwargs: Any,
) -> Any:
    """在独立进程中执行函数；真实等待超时后终止进程并抛出 TimeoutError。

    函数及参数必须可由 spawn 序列化。worker 自身异常会转换为 InjectionError，
    防止把代码错误误记为一次成功的 timeout 注入。
    """
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ConfigurationError("timeout_seconds 必须是有限正数")

    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    process = context.Process(target=_worker_entry, args=(function, args, kwargs, output))
    started = time.monotonic()
    process.start()
    try:
        try:
            message = output.get(timeout=timeout_seconds)
        except queue.Empty:
            _stop_worker(process)
            elapsed = time.monotonic() - started
            pid = process.pid
            if pid is None:
                raise InjectionError("工具子进程超时后缺少 PID，无法形成终止证据") from None
            raise ProcessTimeoutError(
                f"tool process exceeded {timeout_seconds:.3f}s and was terminated",
                worker_pid=pid,
                elapsed_seconds=elapsed,
            ) from None

        # 收到结果仍要等待正常退出，避免留下仅已完成通信但尚未退出的 worker。
        process.join(timeout=5)
        if process.is_alive():
            _stop_worker(process)
            raise InjectionError(f"工具子进程 {process.pid} 返回结果后未正常退出")
        if message.get("status") != "ok":
            raise InjectionError(
                "工具子进程执行失败："
                f"{message.get('error_type', 'UnknownError')}: {message.get('message', '')}"
            )
        return message.get("result")
    finally:
        if process.is_alive():
            _stop_worker(process)
        process.close()
        output.close()
        output.join_thread()
