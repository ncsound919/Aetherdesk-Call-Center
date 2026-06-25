from datetime import UTC, datetime

import structlog

from api.services.db_data_lineage import (
    create_lineage_entry_db,
    get_column_lineage_db,
    get_data_health_score_db,
    get_lineage_graph_db,
    get_record_lineage_db,
)

logger = structlog.get_logger()


class DataLineageService:
    async def record_lineage(
        self,
        tenant_id: str,
        source_table: str,
        source_id: str,
        target_table: str,
        target_id: str,
        operation: str,
        metadata: dict | None = None,
    ) -> dict:
        logger.info(
            "record_lineage",
            tenant_id=tenant_id,
            source=f"{source_table}:{source_id}",
            target=f"{target_table}:{target_id}",
            operation=operation,
        )
        result = await create_lineage_entry_db(
            tenant_id, source_table, source_id,
            target_table, target_id, operation,
            metadata_json=metadata or {},
        )
        if result:
            return {
                "success": True,
                "data": result,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        return {
            "success": False,
            "error": "Failed to record lineage entry",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_lineage_for_record(self, tenant_id: str, table: str, record_id: str) -> dict:
        logger.info("get_lineage_for_record", tenant_id=tenant_id, table=table, record_id=record_id)
        entries = await get_record_lineage_db(tenant_id, table, record_id)
        return {
            "success": True,
            "data": {
                "record": {"table": table, "id": record_id},
                "lineage": entries or [],
                "total": len(entries or []),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_lineage_graph(self, tenant_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
        logger.info("get_lineage_graph", tenant_id=tenant_id)
        entries = await get_lineage_graph_db(tenant_id, start_date=start_date, end_date=end_date)
        nodes = set()
        edges = []
        for entry in entries or []:
            src_key = f"{entry.get('source_table', '')}:{entry.get('source_id', '')}"
            tgt_key = f"{entry.get('target_table', '')}:{entry.get('target_id', '')}"
            nodes.add(src_key)
            nodes.add(tgt_key)
            edges.append({
                "source": src_key,
                "target": tgt_key,
                "operation": entry.get("operation", ""),
                "column": entry.get("column_name"),
                "created_at": entry.get("created_at"),
            })
        return {
            "success": True,
            "data": {
                "nodes": [{"id": n, "table": n.split(":")[0], "record_id": n.split(":")[1] if ":" in n else ""} for n in nodes],
                "edges": edges,
                "total_entries": len(entries or []),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_column_lineage(self, tenant_id: str, table: str, column: str) -> dict:
        logger.info("get_column_lineage", tenant_id=tenant_id, table=table, column=column)
        entries = await get_column_lineage_db(tenant_id, table, column)
        return {
            "success": True,
            "data": {
                "table": table,
                "column": column,
                "lineage": entries or [],
                "total": len(entries or []),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_data_health_score(self, tenant_id: str) -> dict:
        logger.info("get_data_health_score", tenant_id=tenant_id)
        score = await get_data_health_score_db(tenant_id)
        return {
            "success": True,
            "data": score,
            "timestamp": datetime.now(UTC).isoformat(),
        }


lineage_service = DataLineageService()
