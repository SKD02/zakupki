from typing import Optional


def _table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table_name,))
    row = cur.fetchone()
    return bool(row and row.get("exists"))


def _column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = %s
        ) AS exists
        """,
        (table_name, column_name),
    )
    row = cur.fetchone()
    return bool(row and row.get("exists"))


def ensure_unit_names_storage(cur):
    """Нормализует рабочие таблицы к хранению кода единицы измерения.

    В БД в колонках unit хранится unit_code, чтобы не нарушать внешние ключи
    materials.unit -> units.unit_code и purchase_application_items.unit -> units.unit_code.
    В API единица отображается через COALESCE(units.unit_name, unit), поэтому пользователь
    видит "шт", "уп" и т.п., а справочник остаётся защитой от дублей "шт/штука/шт.".
    """
    if not _table_exists(cur, "units"):
        return

    for table_name in ("materials", "purchase_application_items"):
        if not _table_exists(cur, table_name) or not _column_exists(cur, table_name, "unit"):
            continue

        # Если в старых данных в рабочей таблице лежит название единицы (например, "шт"),
        # возвращаем в FK-безопасное значение unit_code (например, U19).
        cur.execute(
            f"""
            UPDATE {table_name} t
            SET unit = u.unit_code
            FROM units u
            WHERE t.unit IS NOT NULL
              AND u.unit_code IS NOT NULL
              AND btrim(u.unit_code) <> ''
              AND lower(btrim(t.unit)) = lower(btrim(u.unit_name))
              AND lower(btrim(t.unit)) <> lower(btrim(u.unit_code))
            """
        )


def resolve_unit(cur, unit_value: Optional[str]) -> Optional[dict]:
    """Возвращает канонические код и наименование единицы по введённому коду/названию."""
    if unit_value is None:
        return None

    if not _table_exists(cur, "units"):
        return None

    unit_value = str(unit_value).strip()
    if not unit_value:
        return None

    cur.execute(
        """
        SELECT unit_code, unit_name
        FROM units
        WHERE lower(btrim(unit_code)) = lower(btrim(%s))
           OR lower(btrim(unit_name)) = lower(btrim(%s))
        ORDER BY
            CASE WHEN lower(btrim(unit_name)) = lower(btrim(%s)) THEN 0 ELSE 1 END,
            unit_code
        LIMIT 1
        """,
        (unit_value, unit_value, unit_value),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def resolve_unit_code(cur, unit_value: Optional[str]) -> Optional[str]:
    unit = resolve_unit(cur, unit_value)
    return unit.get("unit_code") if unit else None


def resolve_unit_name(cur, unit_value: Optional[str]) -> Optional[str]:
    unit = resolve_unit(cur, unit_value)
    return unit.get("unit_name") if unit else None
