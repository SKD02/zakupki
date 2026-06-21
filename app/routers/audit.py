from fastapi import APIRouter

from app.database import get_connection
from app.services.audit import ensure_audit_log_schema

router = APIRouter()


@router.get("")
@router.get("/")
def get_audit_log(limit: int = 300):
    safe_limit = max(1, min(int(limit or 300), 1000))

    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_audit_log_schema(cur)
            cur.execute(
                """
                SELECT
                    log_id,
                    entity_type,
                    entity_id,
                    action,
                    actor,
                    details,
                    created_at
                FROM audit_log
                ORDER BY created_at DESC, log_id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = cur.fetchall()
            conn.commit()
            return rows
