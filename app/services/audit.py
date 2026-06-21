import json

from psycopg2.extras import Json


DEFAULT_ACTOR = "Не определён (авторизация не включена)"


def ensure_audit_log_schema(cur):
    """Создаёт журнал действий. Пользователь пока не определяется, поэтому actor фиксируется как системный."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id bigserial PRIMARY KEY,
            entity_type text NOT NULL,
            entity_id text NULL,
            action text NOT NULL,
            actor text DEFAULT 'Не определён (авторизация не включена)' NOT NULL,
            details jsonb NULL,
            created_at timestamptz DEFAULT now() NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
        ON audit_log(created_at DESC)
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_log_entity
        ON audit_log(entity_type, entity_id)
        """
    )


def log_action(cur, entity_type: str, entity_id=None, action: str = "CHANGE", details=None, actor: str  = None):
    """Пишет действие в журнал. Ошибки журналирования не должны ломать бизнес-операцию."""
    try:
        ensure_audit_log_schema(cur)
        cur.execute(
            """
            INSERT INTO audit_log (entity_type, entity_id, action, actor, details)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (
                str(entity_type),
                str(entity_id) if entity_id is not None else None,
                str(action),
                actor or DEFAULT_ACTOR,
                Json(details or {}, dumps=lambda obj: json.dumps(obj, ensure_ascii=False, default=str)),
            ),
        )
    except Exception:
        # Журнал не должен блокировать основные действия, особенно пока нет авторизации/ролей.
        pass
