"""MySQL SQL 与事务契约测试；不启动本机 mysql80 服务。"""

from pathlib import Path

import pytest

pymysql = pytest.importorskip("pymysql")

from faultlattice.adapters.mysql_index import PyMySQLRunIndex  # noqa: E402
from faultlattice.errors import AdapterCapabilityError, ConfigurationError  # noqa: E402
from faultlattice.indexing import load_run_index_record  # noqa: E402

SAMPLE = (
    Path(__file__).resolve().parent.parent.parent
    / "runs"
    / "_sample"
    / "20261124T124335-94ebab0a"
)


class FakeCursor:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.connection.statements.append(sql)

    def executemany(self, sql: str, parameters: list[dict]) -> None:
        if self.connection.fail_insert:
            raise RuntimeError("simulated insert failure")
        self.connection.statements.append(sql)
        self.connection.parameters = parameters


class FakeConnection:
    def __init__(self, *, fail_insert: bool = False) -> None:
        self.fail_insert = fail_insert
        self.statements = []
        self.parameters = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_mysql_rebuild_uses_schema_delete_insert_and_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    index = PyMySQLRunIndex(
        host="127.0.0.1", port=3306, user="test", password="secret", database="faultlattice"
    )
    connection = FakeConnection()
    monkeypatch.setattr(index, "_connect", lambda: connection)
    record = load_run_index_record(SAMPLE)
    assert index.rebuild([record]) == 1
    assert "CREATE TABLE IF NOT EXISTS faultlattice_runs" in connection.statements[0]
    assert connection.statements[1] == "DELETE FROM faultlattice_runs"
    assert "INSERT INTO faultlattice_runs" in connection.statements[2]
    parameters = connection.parameters[0]
    assert parameters["run_id"] == SAMPLE.name
    assert parameters["created_at"].tzinfo is None
    assert parameters["target_layers"] == '["framework"]'
    assert "secret" not in str(parameters)
    assert connection.committed and connection.closed and not connection.rolled_back


def test_mysql_rebuild_rolls_back_partial_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    index = PyMySQLRunIndex(
        host="127.0.0.1", port=3306, user="test", password="", database="faultlattice"
    )
    connection = FakeConnection(fail_insert=True)
    monkeypatch.setattr(index, "_connect", lambda: connection)
    with pytest.raises(AdapterCapabilityError, match="索引重建失败"):
        index.rebuild([load_run_index_record(SAMPLE)])
    assert connection.rolled_back and connection.closed and not connection.committed


def test_mysql_environment_requires_explicit_user_and_database() -> None:
    with pytest.raises(ConfigurationError, match="MYSQL_USER"):
        PyMySQLRunIndex.from_env({})
    index = PyMySQLRunIndex.from_env(
        {"FAULTLATTICE_MYSQL_USER": "reader", "FAULTLATTICE_MYSQL_DATABASE": "runs"}
    )
    assert index._config["host"] == "127.0.0.1"
    assert index._config["port"] == 3306
