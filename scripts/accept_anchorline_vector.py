"""Anchorline 真实向量验收；不打印凭据，不修改原项目源码。

运行前准备本机 .env、独立 MySQL 测试数据库和 Anchorline 工作区源码副本。
脚本只使用专用事实键，结束后通过生产 forget/delete_fact 清理当前值与向量。
"""
from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from faultlattice.env import load_env  # noqa: E402

load_env(ROOT / ".env")

from external_agents.drafts.anchorline import AnchorlineHostAdapter  # noqa: E402

ENTITY = "faultlattice.acceptance.vector"
ATTRIBUTE = "anchorline_bge_m3_lancedb"
VALUE = "Anchorline real embedding and LanceDB acceptance 2026-11-27"
adapter = AnchorlineHostAdapter()
adapter.preflight(None)

# 外部源码由适配器在预检时加入 sys.path；动态导入也让公共类型检查无需私有源码。
config_module = importlib.import_module("anchorline.config")
store_module = importlib.import_module("anchorline.memory.store")
facts_index = importlib.import_module("anchorline.retrieval.facts_index")
retrieval_store = importlib.import_module("anchorline.retrieval.store")
Settings = config_module.Settings
FactStore = store_module.FactStore
open_lancedb = retrieval_store.open_lancedb


def remove_current() -> None:
    """只失效专用当前事实并删除其向量，保留 MySQL 历史记录。"""
    factory, engine = adapter._session_factory()
    session = factory()
    try:
        current = FactStore(session).current(ENTITY, ATTRIBUTE)
        if current is not None:
            fact_id = current.id
            FactStore(session).forget(ENTITY, ATTRIBUTE)
            assert facts_index.delete_fact(fact_id) is True
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    remove_current()
    fact_id: str | None = None
    try:
        result = adapter.run_script(
            [
                {
                    "tool_call": {
                        "name": "memory_write",
                        "args": {"entity_id": ENTITY, "attribute": ATTRIBUTE, "value": VALUE},
                    }
                },
                {"final_answer": "向量验收事实已写入。"},
            ],
            sandbox=ROOT / ".verify" / "anchorline-vector-acceptance",
        )
        assert result.framework_outcome == "completed"
        tool_event = next(event for event in result.events if event.get("kind") == "tool_result")
        fact_id = str(tool_event["result"]["meta"]["fact_id"])

        factory, engine = adapter._session_factory()
        session = factory()
        try:
            current = FactStore(session).current(ENTITY, ATTRIBUTE)
            assert current is not None and current.id == fact_id and current.value == VALUE
            text = facts_index.fact_text(current)
        finally:
            session.close()
            engine.dispose()

        settings = Settings()
        assert settings.siliconflow_embedding_model == "BAAI/bge-m3"
        table = open_lancedb().open_table(facts_index.TABLE)
        rows = [row for row in table.to_arrow().to_pylist() if row["id"] == fact_id]
        assert len(rows) == 1
        vector = [float(value) for value in rows[0]["vector"]]
        assert len(vector) == 1024
        assert all(math.isfinite(value) for value in vector)
        norm = math.sqrt(sum(value * value for value in vector))
        assert norm > 0
        assert rows[0]["entity_id"] == ENTITY
        assert rows[0]["attribute"] == ATTRIBUTE
        assert rows[0]["value"] == VALUE

        hits = facts_index.search_vector(text, k=5, settings=settings)
        assert hits and hits[0][0] == fact_id
        output = {
            "status": "passed",
            "provider_model": settings.siliconflow_embedding_model,
            "fact_id": fact_id,
            "mysql_current_value_matches": True,
            "lancedb_matching_rows": len(rows),
            "dimensions": len(vector),
            "all_finite": True,
            "nonzero_norm": True,
            "query_top1_fact_id": hits[0][0],
            "query_top1_matches": hits[0][0] == fact_id,
            "index_root": ".verify/anchorline-lancedb",
        }
        output_path = ROOT / ".verify" / "anchorline-vector-acceptance-result.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(output, ensure_ascii=False))
    finally:
        remove_current()


if __name__ == "__main__":
    main()
