"""run_all.py 的环境、端口与跨平台命令测试。"""

import json
import os
import socket
import sys
from pathlib import Path

import run_all


def test_load_env_preserves_existing_values(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nFAULTLATTICE_SERVER_PORT=9001\nexport FAULTLATTICE_CLIENT_PORT='9002'\n",
        encoding="utf-8",
    )
    environ = {"FAULTLATTICE_SERVER_PORT": "8001"}
    run_all.load_env(path, environ)
    assert environ == {"FAULTLATTICE_SERVER_PORT": "8001", "FAULTLATTICE_CLIENT_PORT": "9002"}


def test_child_environment_prefers_current_python() -> None:
    env = run_all.build_environment(8001, 7100, {})
    python_bin = str(Path(sys.executable).absolute().parent)
    assert env["PATH"].split(os.pathsep)[0] == python_bin
    assert env["FAULTLATTICE_SERVER_PORT"] == "8001"
    assert env["FAULTLATTICE_CLIENT_PORT"] == "7100"


def test_port_available_detects_bound_socket() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert run_all.port_available(port) is False
    assert run_all.port_available(port) is True


def test_server_command_uses_current_python_and_reload() -> None:
    command = run_all.server_command(8001)
    assert command[0] == sys.executable
    assert "console.server.app:app" in command
    assert "--reload" in command
    assert command[-1] == "8001"


def test_client_command_uses_npm_and_forwards_vite_port() -> None:
    command = run_all.client_command(5173)
    assert Path(command[0]).name.lower() in {"npm", "npm.cmd"}
    assert "dev:vite" in command
    assert command[-1] == "5173"
    assert "--host" in command


def test_cli_supports_only_modes_and_custom_ports() -> None:
    args = run_all.build_parser().parse_args(
        ["--only", "client", "--port", "9001", "--client-port", "9002"]
    )
    assert args.only == "client"
    assert args.port == 9001
    assert args.client_port == 9002


def test_scripts_use_loopback_only() -> None:
    assert "127.0.0.1" in run_all.server_command(8001)
    assert "127.0.0.1" in run_all.client_command(5173)
    assert os.name in {"nt", "posix"}


def test_npm_preview_uses_project_python_without_uv() -> None:
    root = Path(__file__).resolve().parents[2]
    for package_path in (root / "package.json", root / "console" / "web" / "package.json"):
        scripts = json.loads(package_path.read_text(encoding="utf-8"))["scripts"]
        assert "dev_preview.mjs" in scripts["dev"]
        assert "uv" not in scripts["dev"]
    assert (root / "scripts" / "dev_preview.mjs").is_file()


def test_pyright_config_pins_project_venv() -> None:
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "pyrightconfig.json").read_text(encoding="utf-8"))
    assert config["venvPath"] == "."
    assert config["venv"] == ".venv"


def test_workspace_preview_forwards_port_to_vite(monkeypatch, tmp_path: Path) -> None:
    import scripts.dev_preview

    monkeypatch.delenv("FAULTLATTICE_SERVER_PORT", raising=False)
    monkeypatch.setattr(scripts.dev_preview, "ENV_FILE", tmp_path / "missing.env")
    assert scripts.dev_preview.preview_args(
        ["--host", "127.0.0.1", "--port", "7100"], server_ready=lambda _port: False
    ) == ["--client-port", "7100", "--port", "8001"]


def test_workspace_preview_reuses_healthy_existing_server(monkeypatch, tmp_path: Path) -> None:
    import scripts.dev_preview

    monkeypatch.delenv("FAULTLATTICE_SERVER_PORT", raising=False)
    monkeypatch.setattr(scripts.dev_preview, "ENV_FILE", tmp_path / "missing.env")
    assert scripts.dev_preview.preview_args(
        ["--port", "7100"], server_ready=lambda _port: True
    ) == [
        "--only",
        "client",
        "--client-port",
        "7100",
        "--port",
        "8001",
    ]


def test_workspace_preview_env_file_overrides_inherited_port(
    monkeypatch, tmp_path: Path
) -> None:
    import scripts.dev_preview

    env_file = tmp_path / ".env"
    env_file.write_text("FAULTLATTICE_SERVER_PORT=8002\n", encoding="utf-8")
    monkeypatch.setattr(scripts.dev_preview, "ENV_FILE", env_file)
    monkeypatch.setenv("FAULTLATTICE_SERVER_PORT", "8001")
    assert scripts.dev_preview.preview_args(
        ["--port", "7100"], server_ready=lambda _port: True
    ) == ["--only", "client", "--client-port", "7100", "--port", "8002"]
