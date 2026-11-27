"""MySQL 可重建结构索引；原始 runs/ 四件套仍是唯一事实来源。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC

import pymysql

from faultlattice.canonical import canonical_dumps
from faultlattice.errors import AdapterCapabilityError, ConfigurationError
from faultlattice.indexing import RunIndexRecord

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS faultlattice_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    created_at DATETIME(6) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    expected_behavior TEXT NOT NULL,
    host VARCHAR(64) NOT NULL,
    host_package_version VARCHAR(128) NULL,
    mode VARCHAR(2) NOT NULL,
    experiment_family VARCHAR(32) NULL,
    injection_point VARCHAR(32) NULL,
    fault_type VARCHAR(64) NULL,
    surface_as VARCHAR(32) NULL,
    target_layers JSON NOT NULL,
    injection_applied BOOLEAN NOT NULL,
    observation_status VARCHAR(32) NOT NULL,
    framework_verdict VARCHAR(64) NULL,
    model_verdict VARCHAR(64) NULL,
    run_dir TEXT NOT NULL,
    manifest_sha256 CHAR(64) NOT NULL,
    search_text LONGTEXT NOT NULL,
    INDEX idx_faultlattice_fault (host, mode, experiment_family, fault_type),
    INDEX idx_faultlattice_created (created_at),
    INDEX idx_faultlattice_manifest (manifest_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

INSERT_SQL = """
INSERT INTO faultlattice_runs (
    run_id, created_at, task_id, description, expected_behavior, host,
    host_package_version, mode, experiment_family, injection_point, fault_type,
    surface_as, target_layers, injection_applied, observation_status,
    framework_verdict, model_verdict, run_dir, manifest_sha256, search_text
) VALUES (
    %(run_id)s, %(created_at)s, %(task_id)s, %(description)s, %(expected_behavior)s,
    %(host)s, %(host_package_version)s, %(mode)s, %(experiment_family)s,
    %(injection_point)s, %(fault_type)s, %(surface_as)s, %(target_layers)s,
    %(injection_applied)s, %(observation_status)s, %(framework_verdict)s,
    %(model_verdict)s, %(run_dir)s, %(manifest_sha256)s, %(search_text)s
)
"""


class PyMySQLRunIndex:
    """用事务重建派生表；失败时回滚，不把半批索引当成完成。"""

    def __init__(
        self, *, host: str, port: int, user: str, password: str, database: str
    ) -> None:
        self._config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "charset": "utf8mb4",
            "autocommit": False,
            "connect_timeout": 5,
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> PyMySQLRunIndex:
        values = os.environ if env is None else env
        user = values.get("FAULTLATTICE_MYSQL_USER", "").strip()
        database = values.get("FAULTLATTICE_MYSQL_DATABASE", "").strip()
        if not user or not database:
            raise ConfigurationError(
                "MySQL 索引需要 FAULTLATTICE_MYSQL_USER 与 FAULTLATTICE_MYSQL_DATABASE"
            )
        try:
            port = int(values.get("FAULTLATTICE_MYSQL_PORT", "3306"))
        except ValueError as exc:
            raise ConfigurationError("FAULTLATTICE_MYSQL_PORT 必须是整数") from exc
        return cls(
            host=values.get("FAULTLATTICE_MYSQL_HOST", "127.0.0.1").strip(),
            port=port,
            user=user,
            password=values.get("FAULTLATTICE_MYSQL_PASSWORD", ""),
            database=database,
        )

    def _connect(self):
        return pymysql.connect(**self._config)

    @staticmethod
    def _parameters(record: RunIndexRecord) -> dict[str, object]:
        values = record.model_dump(mode="python")
        values["created_at"] = record.created_at.astimezone(UTC).replace(tzinfo=None)
        values["mode"] = record.mode.value
        values["target_layers"] = canonical_dumps(record.target_layers)
        return values

    def rebuild(self, records: list[RunIndexRecord]) -> int:
        """重建全部记录并返回实际写入数；异常消息不携带连接密码。"""
        try:
            connection = self._connect()
        except Exception as exc:
            raise AdapterCapabilityError(f"MySQL 连接失败: {type(exc).__name__}") from exc
        try:
            with connection.cursor() as cursor:
                cursor.execute(SCHEMA_SQL)
                cursor.execute("DELETE FROM faultlattice_runs")
                if records:
                    cursor.executemany(INSERT_SQL, [self._parameters(item) for item in records])
            connection.commit()
            return len(records)
        except Exception as exc:
            connection.rollback()
            raise AdapterCapabilityError(f"MySQL 索引重建失败: {type(exc).__name__}") from exc
        finally:
            connection.close()
