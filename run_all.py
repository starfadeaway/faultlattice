"""启动 FaultLattice 本地 FastAPI 与 React 研发控制台。

仅绑定 127.0.0.1，不对外开放。后端使用 uvicorn reload，前端使用 Vite HMR；
任一服务异常退出或收到 Ctrl+C 时，统一清理另一服务及其子进程。
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import MutableMapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_env(path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """保留启动器兼容入口；实现位于可安装核心包，供 CLI 独立使用。"""
    from faultlattice.env import load_env as load_env_file

    load_env_file(path, environ)


def port_available(port: int, host: str = "127.0.0.1") -> bool:
    """启动前实际绑定端口；失败表示端口被占用或当前地址不可绑定。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError:
        return False
    return True


def _npm_command() -> str:
    executable = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if executable is None:
        raise RuntimeError("找不到 npm；请安装 Node.js 后再启动研发控制台")
    return executable


def server_command(port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "console.server.app:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def client_command(client_port: int) -> list[str]:
    return [
        _npm_command(),
        "run",
        "dev:vite",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(client_port),
    ]


def _start(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    kwargs: dict[str, object] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, cwd=cwd, env=env, **kwargs)  # type: ignore[arg-type]


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            # npm.cmd 与 uvicorn reload 都有子进程，必须清理整棵进程树。
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=8)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 FaultLattice 本地研发控制台")
    parser.add_argument("--only", choices=("both", "server", "client"), default="both")
    parser.add_argument("--port", type=int, default=None, help="FastAPI 端口，默认 8001")
    parser.add_argument("--client-port", type=int, default=None, help="Vite 端口，默认 5173")
    return parser


def build_environment(
    server_port: int,
    client_port: int,
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """让服务及其验收子进程优先使用启动器所在的 Python 环境。"""
    env = dict(os.environ if environ is None else environ)
    python_bin = str(Path(sys.executable).absolute().parent)
    env["PATH"] = os.pathsep.join(filter(None, (python_bin, env.get("PATH", ""))))
    env["FAULTLATTICE_SERVER_PORT"] = str(server_port)
    env["FAULTLATTICE_CLIENT_PORT"] = str(client_port)
    return env


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env(ROOT / ".env")
    server_port = args.port or int(os.environ.get("FAULTLATTICE_SERVER_PORT", "8001"))
    client_port = args.client_port or int(os.environ.get("FAULTLATTICE_CLIENT_PORT", "5173"))

    selected = []
    if args.only in ("both", "server"):
        selected.append(("FastAPI", server_port))
    if args.only in ("both", "client"):
        selected.append(("Vite", client_port))
    for name, port in selected:
        if not 1 <= port <= 65535:
            print(f"[错误] {name} 端口超出范围: {port}", file=sys.stderr)
            return 2
        if not port_available(port):
            print(f"[错误] {name} 端口已被占用: 127.0.0.1:{port}", file=sys.stderr)
            return 2

    env = build_environment(server_port, client_port)
    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        if args.only in ("both", "server"):
            processes.append(("FastAPI", _start(server_command(server_port), ROOT, env)))
            print(f"FastAPI: http://127.0.0.1:{server_port}/api/health")
        if args.only in ("both", "client"):
            processes.append(
                ("Vite", _start(client_command(client_port), ROOT / "console" / "web", env))
            )
            print(f"研发视图: http://127.0.0.1:{client_port}/")

        while True:
            for name, process in processes:
                returncode = process.poll()
                if returncode is not None:
                    print(f"[错误] {name} 已退出，退出码 {returncode}；正在清理其他服务", file=sys.stderr)
                    return returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在停止 FaultLattice 研发控制台……")
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"[错误] 服务启动失败: {exc}", file=sys.stderr)
        return 2
    finally:
        for _, process in reversed(processes):
            _stop(process)


if __name__ == "__main__":
    sys.exit(main())
