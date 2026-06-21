SUPPLIER_ID_PREFIX = "SUPL"
SUPPLIER_ID_DIGITS = 6
SUPPLIER_ID_REGEX = r"^SUPL[0-9]{6}$"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_table(table_name: str) -> str:
    return ".".join(_quote_identifier(part) for part in table_name.split("."))


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


def _drop_foreign_keys_to_supplier_id(cur):
    if not _table_exists(cur, "suppliers"):
        return

    cur.execute(
        """
        SELECT c.conrelid::regclass::text AS table_name, c.conname
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.confrelid
         AND a.attnum = ANY(c.confkey)
        WHERE c.contype = 'f'
          AND c.confrelid = 'suppliers'::regclass
          AND a.attname = 'supplier_id'
        """
    )

    for row in cur.fetchall():
        cur.execute(
            f"ALTER TABLE {_quote_table(row['table_name'])} DROP CONSTRAINT IF EXISTS {_quote_identifier(row['conname'])}"
        )


def _alter_supplier_id_column_to_text(cur, table_name: str):
    if not _table_exists(cur, table_name) or not _column_exists(cur, table_name, "supplier_id"):
        return

    cur.execute(
        f"""
        ALTER TABLE {_quote_table(table_name)}
        ALTER COLUMN supplier_id DROP DEFAULT
        """
    )
    cur.execute(
        f"""
        ALTER TABLE {_quote_table(table_name)}
        ALTER COLUMN supplier_id TYPE text USING supplier_id::text
        """
    )


MISSING_REFERENCE_MARKERS = {"#н/д", "н/д", "#n/a", "n/a", "na", "nan", "none", "null", "-", "—"}


def is_missing_reference(value) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text.lower().replace("ё", "е") in MISSING_REFERENCE_MARKERS


def sanitize_supplier_okved2(cur):
    """Удаляет из suppliers невалидные значения ОКВЭД2 до любых UPDATE этой таблицы.

    Иначе даже UPDATE supplier_id падает на внешнем ключе fk_suppliers_okved2,
    если в старых данных лежит #Н/Д/#N/A или код, отсутствующий в справочнике okved2.
    """
    if (
        not _table_exists(cur, "suppliers")
        or not _column_exists(cur, "suppliers", "okved2_code")
        or not _table_exists(cur, "okved2")
    ):
        return

    cur.execute("ALTER TABLE suppliers ALTER COLUMN okved2_code DROP NOT NULL")
    cur.execute(
        """
        UPDATE suppliers s
        SET okved2_code = NULL
        WHERE s.okved2_code IS NOT NULL
          AND (
              lower(replace(btrim(s.okved2_code), 'ё', 'е')) = ANY(%s)
              OR NOT EXISTS (
                  SELECT 1
                  FROM okved2 o
                  WHERE btrim(o.okved2_code) = btrim(s.okved2_code)
              )
          )
        """,
        (list(MISSING_REFERENCE_MARKERS),),
    )


def resolve_okved2_code(cur, value, *, strict: bool = False):
    """Возвращает существующий код ОКВЭД2 или None для пустых/#Н/Д.

    strict=True используется при ручном создании поставщика: неизвестный непустой код
    возвращает понятную ошибку вместо падения БД по внешнему ключу.
    """
    if is_missing_reference(value):
        return None

    code = str(value).strip()
    if not _table_exists(cur, "okved2"):
        return code

    cur.execute(
        """
        SELECT okved2_code
        FROM okved2
        WHERE btrim(okved2_code) = btrim(%s)
        LIMIT 1
        """,
        (code,),
    )
    row = cur.fetchone()

    if row:
        return row["okved2_code"]

    if strict:
        raise ValueError(f'Код ОКВЭД2 "{code}" отсутствует в справочнике ОКВЭД2')

    return None


def _column_data_type(cur, table_name: str, column_name: str):
    cur.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    row = cur.fetchone()
    return row.get("data_type") if row else None


def _supplier_id_schema_ready(cur) -> bool:
    """Быстрая проверка, чтобы не делать ALTER/UPDATE при каждом GET.

    На страницах мэппингов несколько запросов приходят параллельно. Если каждый из них
    запускает ALTER TABLE suppliers/user_group_supply_map, PostgreSQL может поймать
    взаимоблокировку с обычными SELECT. Поэтому тяжёлая миграция выполняется только
    когда реально есть старые bigint/не-масочные ID.
    """
    if not _table_exists(cur, "suppliers") or not _column_exists(cur, "suppliers", "supplier_id"):
        return True

    supplier_type = _column_data_type(cur, "suppliers", "supplier_id")
    if supplier_type not in {"text", "character varying"}:
        return False

    cur.execute(
        f"""
        SELECT EXISTS (
            SELECT 1
            FROM suppliers
            WHERE supplier_id IS NULL
               OR supplier_id::text !~ '^{SUPPLIER_ID_PREFIX}[0-9]{{{SUPPLIER_ID_DIGITS}}}$'
        ) AS has_bad_ids
        """
    )
    row = cur.fetchone()
    if row and row.get("has_bad_ids"):
        return False

    related_tables = [
        "user_group_supply_map",
        "supplier_financials",
        "supplier_search_results",
        "procurement_email_batches",
    ]

    for table_name in related_tables:
        if not _table_exists(cur, table_name):
            continue
        if table_name == "user_group_supply_map" and not _column_exists(cur, table_name, "supplier_id"):
            return False
        if _column_exists(cur, table_name, "supplier_id"):
            column_type = _column_data_type(cur, table_name, "supplier_id")
            if column_type not in {"text", "character varying"}:
                return False

    if _column_exists(cur, "suppliers", "okved2_code") and _table_exists(cur, "okved2"):
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM suppliers s
                WHERE s.okved2_code IS NOT NULL
                  AND (
                      lower(replace(btrim(s.okved2_code), 'ё', 'е')) = ANY(%s)
                      OR NOT EXISTS (
                          SELECT 1
                          FROM okved2 o
                          WHERE btrim(o.okved2_code) = btrim(s.okved2_code)
                      )
                  )
            ) AS has_bad_okved2
            """,
            (list(MISSING_REFERENCE_MARKERS),),
        )
        row = cur.fetchone()
        if row and row.get("has_bad_okved2"):
            return False

    return True


def ensure_supplier_id_schema(cur):
    """Приводит ID поставщиков к маске SUPLXXXXXX и к типу text во всех рабочих таблицах."""
    if not _table_exists(cur, "suppliers") or not _column_exists(cur, "suppliers", "supplier_id"):
        return

    if _supplier_id_schema_ready(cur):
        return

    # Сериализуем редкую миграцию schema/data, чтобы параллельные GET страниц
    # мэппинга не конкурировали за AccessExclusiveLock на suppliers.
    cur.execute("SELECT pg_advisory_xact_lock(hashtext('ensure_supplier_id_schema')::bigint)")

    if _supplier_id_schema_ready(cur):
        return

    sanitize_supplier_okved2(cur)
    _drop_foreign_keys_to_supplier_id(cur)

    cur.execute("DROP TABLE IF EXISTS tmp_supplier_id_map")
    cur.execute(
        f"""
        CREATE TEMP TABLE tmp_supplier_id_map ON COMMIT DROP AS
        WITH existing_max AS (
            SELECT COALESCE(MAX(substring(supplier_id::text FROM '^{SUPPLIER_ID_PREFIX}([0-9]{{{SUPPLIER_ID_DIGITS}}})$')::int), 0) AS max_no
            FROM suppliers
            WHERE supplier_id::text ~ '^{SUPPLIER_ID_PREFIX}[0-9]{{{SUPPLIER_ID_DIGITS}}}$'
        ),
        non_masked AS (
            SELECT
                supplier_id::text AS old_id,
                row_number() OVER (ORDER BY supplier_id::text) AS rn
            FROM suppliers
            WHERE supplier_id::text !~ '^{SUPPLIER_ID_PREFIX}[0-9]{{{SUPPLIER_ID_DIGITS}}}$'
        )
        SELECT
            s.supplier_id::text AS old_id,
            CASE
                WHEN s.supplier_id::text ~ '^{SUPPLIER_ID_PREFIX}[0-9]{{{SUPPLIER_ID_DIGITS}}}$'
                    THEN s.supplier_id::text
                ELSE '{SUPPLIER_ID_PREFIX}' || lpad((existing_max.max_no + non_masked.rn)::text, {SUPPLIER_ID_DIGITS}, '0')
            END AS new_id
        FROM suppliers s
        CROSS JOIN existing_max
        LEFT JOIN non_masked
          ON non_masked.old_id = s.supplier_id::text
        """
    )

    related_tables = [
        "user_group_supply_map",
        "supplier_financials",
        "supplier_search_results",
        "procurement_email_batches",
    ]

    for table_name in related_tables:
        if table_name == "user_group_supply_map" and _table_exists(cur, table_name) and not _column_exists(cur, table_name, "supplier_id"):
            cur.execute("ALTER TABLE user_group_supply_map ADD COLUMN supplier_id text")
        _alter_supplier_id_column_to_text(cur, table_name)

    _alter_supplier_id_column_to_text(cur, "suppliers")
    cur.execute("ALTER TABLE suppliers ALTER COLUMN supplier_id DROP DEFAULT")

    for table_name in related_tables + ["suppliers"]:
        if not _table_exists(cur, table_name) or not _column_exists(cur, table_name, "supplier_id"):
            continue

        cur.execute(
            f"""
            UPDATE {_quote_table(table_name)} t
            SET supplier_id = m.new_id
            FROM tmp_supplier_id_map m
            WHERE t.supplier_id = m.old_id
              AND t.supplier_id IS DISTINCT FROM m.new_id
            """
        )

    if _table_exists(cur, "user_group_supply_map") and _column_exists(cur, "user_group_supply_map", "supplier_id"):
        cur.execute(
            """
            UPDATE user_group_supply_map ugsm
            SET
                supplier_id = s.supplier_id::text,
                inn_supply = COALESCE(ugsm.inn_supply, s.inn)
            FROM suppliers s
            WHERE ugsm.supplier_id IS NOT NULL
              AND btrim(ugsm.supplier_id::text) <> ''
              AND s.inn IS NOT NULL
              AND btrim(s.inn) = btrim(ugsm.supplier_id::text)
            """
        )
        cur.execute(
            """
            UPDATE user_group_supply_map ugsm
            SET supplier_id = s.supplier_id::text
            FROM suppliers s
            WHERE (ugsm.supplier_id IS NULL OR btrim(ugsm.supplier_id::text) = '')
              AND ugsm.inn_supply IS NOT NULL
              AND btrim(s.inn) = btrim(ugsm.inn_supply)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_group_supply_map_supplier_id
            ON user_group_supply_map (supplier_id)
            """
        )


def next_supplier_id(cur) -> str:
    ensure_supplier_id_schema(cur)
    cur.execute(
        f"""
        SELECT COALESCE(MAX(substring(supplier_id::text FROM '^{SUPPLIER_ID_PREFIX}([0-9]{{{SUPPLIER_ID_DIGITS}}})$')::int), 0) + 1 AS next_no
        FROM suppliers
        WHERE supplier_id::text ~ '^{SUPPLIER_ID_PREFIX}[0-9]{{{SUPPLIER_ID_DIGITS}}}$'
        """
    )
    next_no = int(cur.fetchone()["next_no"])

    if next_no > 10 ** SUPPLIER_ID_DIGITS - 1:
        raise ValueError("Превышен лимит ID поставщиков для маски SUPLXXXXXX")

    return f"{SUPPLIER_ID_PREFIX}{next_no:0{SUPPLIER_ID_DIGITS}d}"
