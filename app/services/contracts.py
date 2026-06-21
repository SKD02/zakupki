from fastapi import HTTPException


LEGACY_EMPTY_DATE = "1900-01-01"
DEFAULT_APPENDIX = "-"


def normalize_text(value):
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def normalize_work_doc(value):
    value = normalize_text(value)
    return value.upper() if value else None


def normalize_key(value):
    return str(value or "").strip().lower().replace("ё", "е")


def normalize_appendix(value):
    return normalize_text(value) or DEFAULT_APPENDIX


def contract_base_key(row):
    """Один договор определяется номером договора.

    Дата договора остаётся справочным полем, но не участвует в дроблении реестра,
    потому что в исходной Excel-модели № договора уже является бизнес-ключом.
    Приложение относится к связям договора с РД/предметами.
    """
    return normalize_key(row.get("contract_no"))


def contract_base_display(row):
    date = row.get("contract_date") or "без даты"
    return f"{row['contract_id']} - № {row['contract_no']} от {date}"


def contract_display(row):
    base = contract_base_display(row)
    appendix = row.get("contract_appendix") or row.get("link_contract_appendix") or ""
    subject = row.get("work_doc_subject") or row.get("contract_subject") or ""
    code = row.get("work_doc_code") or ""
    appendix_part = f" / {appendix}" if appendix else ""
    tail = f" / {code} - {subject}" if code or subject else ""
    return f"{base}{appendix_part}{tail}"


def ensure_contract_schema(cur):
    """
    Целевая модель:
    - contracts: одна строка = один договор по номеру договора;
    - contract_work_doc_subjects: приложения + связи договора с шифрами РД и предметами;
    - work_document_subjects: справочник пар шифр РД + предмет.

    Старые данные автоматически консолидируются: если раньше договоры были созданы
    по связке № договора + приложение, они будут объединены до одной строки в contracts,
    а приложения будут перенесены в contract_work_doc_subjects.contract_appendix.
    """
    cur.execute("CREATE SEQUENCE IF NOT EXISTS contract_seq START 1")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS work_document_subjects (
            work_doc_code text NOT NULL,
            work_doc_subject text NOT NULL,
            description text NULL,
            created_at timestamptz DEFAULT now() NOT NULL,
            updated_at timestamptz DEFAULT now() NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contracts (
            contract_id text PRIMARY KEY,
            contract_no text NOT NULL,
            contract_date date NULL,
            contract_appendix text NULL,
            created_at timestamptz DEFAULT now() NOT NULL,
            updated_at timestamptz DEFAULT now() NOT NULL
        )
        """
    )

    cur.execute("ALTER TABLE work_document_subjects ADD COLUMN IF NOT EXISTS description text")
    cur.execute("ALTER TABLE work_document_subjects ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now() NOT NULL")
    cur.execute("ALTER TABLE work_document_subjects ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now() NOT NULL")

    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_date date NULL")
    # legacy-поле оставляем nullable, чтобы старые БД открывались без ручной миграции.
    # Новая логика не заполняет contracts.contract_appendix.
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_appendix text NULL")
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now() NOT NULL")
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now() NOT NULL")

    # Проверяем legacy-колонки старой модели. Если они есть, перенесём их в связи,
    # а в конце миграции удалим из contracts, чтобы в таблице не оставались пустые work_doc_code/work_doc_subject.
    cur.execute(
        """
        SELECT
            EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'contracts' AND column_name = 'work_doc_code'
            ) AS has_work_doc_code,
            EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'contracts' AND column_name = 'work_doc_subject'
            ) AS has_work_doc_subject
        """
    )
    legacy_columns = cur.fetchone()
    has_legacy_work_doc_columns = bool(
        legacy_columns
        and legacy_columns.get("has_work_doc_code")
        and legacy_columns.get("has_work_doc_subject")
    )

    # Снимаем старые FK/индексы перед перестройкой PK.
    cur.execute("ALTER TABLE contracts DROP CONSTRAINT IF EXISTS fk_contracts_work_doc_code")
    cur.execute("ALTER TABLE contracts DROP CONSTRAINT IF EXISTS fk_contracts_work_doc_subject")
    cur.execute("DROP INDEX IF EXISTS ux_contracts_unique_business_key")
    cur.execute("DROP INDEX IF EXISTS ux_contracts_business_base")
    cur.execute("DROP INDEX IF EXISTS ux_contracts_contract_no_date")
    cur.execute("DROP INDEX IF EXISTS ux_contracts_contract_no_only")

    cur.execute(
        """
        DO $$
        DECLARE
            r record;
        BEGIN
            IF to_regclass('contracts') IS NOT NULL THEN
                FOR r IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'contracts'::regclass
                      AND contype = 'f'
                      AND confrelid = 'work_document_subjects'::regclass
                LOOP
                    EXECUTE format('ALTER TABLE contracts DROP CONSTRAINT IF EXISTS %I', r.conname);
                END LOOP;
            END IF;

            IF to_regclass('contract_work_doc_subjects') IS NOT NULL THEN
                FOR r IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'contract_work_doc_subjects'::regclass
                      AND contype = 'f'
                LOOP
                    EXECUTE format('ALTER TABLE contract_work_doc_subjects DROP CONSTRAINT IF EXISTS %I', r.conname);
                END LOOP;
            END IF;
        END $$
        """
    )

    cur.execute("ALTER TABLE work_document_subjects DROP CONSTRAINT IF EXISTS work_document_subjects_pkey")

    # Чистим пустые/дубли РД перед созданием PK.
    cur.execute(
        """
        DELETE FROM work_document_subjects
        WHERE NULLIF(btrim(work_doc_code), '') IS NULL
           OR NULLIF(btrim(work_doc_subject), '') IS NULL
        """
    )
    cur.execute(
        """
        DELETE FROM work_document_subjects wds
        USING (
            SELECT
                ctid,
                row_number() OVER (
                    PARTITION BY upper(btrim(work_doc_code)), lower(btrim(work_doc_subject))
                    ORDER BY created_at NULLS LAST, ctid
                ) AS rn
            FROM work_document_subjects
        ) d
        WHERE wds.ctid = d.ctid
          AND d.rn > 1
        """
    )
    cur.execute(
        """
        ALTER TABLE work_document_subjects
        ADD CONSTRAINT work_document_subjects_pkey
        PRIMARY KEY (work_doc_code, work_doc_subject)
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_work_doc_subjects (
            contract_id text NOT NULL,
            contract_appendix text NOT NULL DEFAULT '-',
            work_doc_code text NOT NULL,
            work_doc_subject text NOT NULL,
            created_at timestamptz DEFAULT now() NOT NULL,
            updated_at timestamptz DEFAULT now() NOT NULL,
            PRIMARY KEY (contract_id, contract_appendix, work_doc_code, work_doc_subject)
        )
        """
    )

    cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS contract_appendix text")
    cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now() NOT NULL")
    cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now() NOT NULL")
    cur.execute("ALTER TABLE contract_work_doc_subjects DROP CONSTRAINT IF EXISTS contract_work_doc_subjects_pkey")

    # Заполняем приложение у уже существующих связей из старого contracts.contract_appendix.
    cur.execute(
        """
        UPDATE contract_work_doc_subjects l
        SET contract_appendix = COALESCE(NULLIF(btrim(l.contract_appendix), ''), NULLIF(btrim(c.contract_appendix), ''), '-')
        FROM contracts c
        WHERE c.contract_id = l.contract_id
          AND NULLIF(btrim(COALESCE(l.contract_appendix, '')), '') IS NULL
        """
    )
    cur.execute("UPDATE contract_work_doc_subjects SET contract_appendix = '-' WHERE NULLIF(btrim(contract_appendix), '') IS NULL")
    cur.execute("ALTER TABLE contract_work_doc_subjects ALTER COLUMN contract_appendix SET DEFAULT '-'")
    cur.execute("ALTER TABLE contract_work_doc_subjects ALTER COLUMN contract_appendix SET NOT NULL")

    # Добавляем в справочник РД legacy-пары из contracts, если они были сохранены в старой модели.
    if has_legacy_work_doc_columns:
        cur.execute(
            """
            INSERT INTO work_document_subjects (work_doc_code, work_doc_subject, description, created_at, updated_at)
            SELECT DISTINCT
                upper(btrim(work_doc_code)),
                btrim(work_doc_subject),
                NULL,
                now(),
                now()
            FROM contracts
            WHERE NULLIF(btrim(work_doc_code), '') IS NOT NULL
              AND NULLIF(btrim(work_doc_subject), '') IS NOT NULL
            ON CONFLICT (work_doc_code, work_doc_subject)
            DO UPDATE SET updated_at = now()
            """
        )

    legacy_work_doc_code_select = "work_doc_code" if has_legacy_work_doc_columns else "NULL::text AS work_doc_code"
    legacy_work_doc_subject_select = "work_doc_subject" if has_legacy_work_doc_columns else "NULL::text AS work_doc_subject"

    # Строим каноническую карту: один keeper_contract_id на один номер договора.
    cur.execute("DROP TABLE IF EXISTS tmp_contract_dedup")
    cur.execute(
        f"""
        CREATE TEMP TABLE tmp_contract_dedup ON COMMIT DROP AS
        SELECT
            contract_id,
            first_value(contract_id) OVER (
                PARTITION BY lower(btrim(contract_no))
                ORDER BY contract_id
            ) AS keeper_contract_id,
            contract_no,
            contract_date,
            contract_appendix,
            {legacy_work_doc_code_select},
            {legacy_work_doc_subject_select},
            created_at,
            updated_at
        FROM contracts
        WHERE NULLIF(btrim(contract_no), '') IS NOT NULL
        """
    )

    # Пересобираем связи в отдельной temp-таблице, чтобы безопасно объединить старые contract_id.
    cur.execute("DROP TABLE IF EXISTS tmp_contract_links")
    cur.execute(
        """
        CREATE TEMP TABLE tmp_contract_links ON COMMIT DROP AS
        SELECT DISTINCT
            d.keeper_contract_id AS contract_id,
            COALESCE(NULLIF(btrim(l.contract_appendix), ''), NULLIF(btrim(d.contract_appendix), ''), '-') AS contract_appendix,
            l.work_doc_code,
            l.work_doc_subject,
            COALESCE(l.created_at, d.created_at, now()) AS created_at,
            now() AS updated_at
        FROM contract_work_doc_subjects l
        JOIN tmp_contract_dedup d ON d.contract_id = l.contract_id
        JOIN work_document_subjects wds
          ON wds.work_doc_code = l.work_doc_code
         AND wds.work_doc_subject = l.work_doc_subject

        UNION

        SELECT DISTINCT
            d.keeper_contract_id AS contract_id,
            COALESCE(NULLIF(btrim(d.contract_appendix), ''), '-') AS contract_appendix,
            wds.work_doc_code,
            wds.work_doc_subject,
            COALESCE(d.created_at, now()) AS created_at,
            now() AS updated_at
        FROM tmp_contract_dedup d
        JOIN work_document_subjects wds
          ON lower(btrim(wds.work_doc_code)) = lower(btrim(d.work_doc_code))
         AND lower(btrim(wds.work_doc_subject)) = lower(btrim(d.work_doc_subject))
        WHERE NULLIF(btrim(d.work_doc_code), '') IS NOT NULL
          AND NULLIF(btrim(d.work_doc_subject), '') IS NOT NULL
        """
    )

    # Если есть загруженные заявки на удаляемые дубль-ID, переводим их на keeper.
    cur.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('purchase_applications') IS NOT NULL THEN
                UPDATE purchase_applications pa
                SET contract_id = d.keeper_contract_id
                FROM tmp_contract_dedup d
                WHERE pa.contract_id = d.contract_id
                  AND d.contract_id <> d.keeper_contract_id;
            END IF;
        END $$
        """
    )

    cur.execute("DELETE FROM contract_work_doc_subjects")
    cur.execute(
        """
        INSERT INTO contract_work_doc_subjects (
            contract_id,
            contract_appendix,
            work_doc_code,
            work_doc_subject,
            created_at,
            updated_at
        )
        SELECT DISTINCT
            contract_id,
            contract_appendix,
            work_doc_code,
            work_doc_subject,
            MIN(created_at) AS created_at,
            MAX(updated_at) AS updated_at
        FROM tmp_contract_links
        GROUP BY contract_id, contract_appendix, work_doc_code, work_doc_subject
        """
    )

    # Удаляем дубли contracts, оставляя одну строку на contract_no.
    cur.execute(
        """
        DELETE FROM contracts c
        USING tmp_contract_dedup d
        WHERE c.contract_id = d.contract_id
          AND d.contract_id <> d.keeper_contract_id
        """
    )

    # В оставшихся договорах приложение не храним: оно живёт в таблице связей.
    cur.execute("UPDATE contracts SET contract_appendix = NULL")
    cur.execute("ALTER TABLE contracts DROP COLUMN IF EXISTS work_doc_code")
    cur.execute("ALTER TABLE contracts DROP COLUMN IF EXISTS work_doc_subject")

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_contracts_contract_no_only
        ON contracts (lower(btrim(contract_no)))
        """
    )

    # Чистим мусорные связи перед PK/FK.
    cur.execute(
        """
        DELETE FROM contract_work_doc_subjects l
        WHERE NOT EXISTS (
            SELECT 1 FROM contracts c WHERE c.contract_id = l.contract_id
        )
        """
    )
    cur.execute(
        """
        DELETE FROM contract_work_doc_subjects l
        WHERE NOT EXISTS (
            SELECT 1
            FROM work_document_subjects wds
            WHERE wds.work_doc_code = l.work_doc_code
              AND wds.work_doc_subject = l.work_doc_subject
        )
        """
    )
    cur.execute(
        """
        DELETE FROM contract_work_doc_subjects l
        USING (
            SELECT
                ctid,
                row_number() OVER (
                    PARTITION BY contract_id, contract_appendix, work_doc_code, work_doc_subject
                    ORDER BY created_at NULLS LAST, ctid
                ) AS rn
            FROM contract_work_doc_subjects
        ) d
        WHERE l.ctid = d.ctid
          AND d.rn > 1
        """
    )

    cur.execute(
        """
        ALTER TABLE contract_work_doc_subjects
        ADD CONSTRAINT contract_work_doc_subjects_pkey
        PRIMARY KEY (contract_id, contract_appendix, work_doc_code, work_doc_subject)
        """
    )

    cur.execute(
        """
        ALTER TABLE contract_work_doc_subjects
        ADD CONSTRAINT fk_contract_links_contract
        FOREIGN KEY (contract_id)
        REFERENCES contracts(contract_id)
        ON DELETE CASCADE
        """
    )

    cur.execute(
        """
        ALTER TABLE contract_work_doc_subjects
        ADD CONSTRAINT fk_contract_links_work_doc_subject
        FOREIGN KEY (work_doc_code, work_doc_subject)
        REFERENCES work_document_subjects(work_doc_code, work_doc_subject)
        ON UPDATE CASCADE
        ON DELETE CASCADE
        """
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_contract_links_work_doc_subject ON contract_work_doc_subjects(work_doc_code, work_doc_subject)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contract_links_contract_id ON contract_work_doc_subjects(contract_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contract_links_appendix ON contract_work_doc_subjects(contract_appendix)")

    # Поднимаем sequence выше существующих DXXXXXX.
    cur.execute(
        """
        SELECT setval(
            'contract_seq',
            GREATEST(
                COALESCE(
                    (
                        SELECT MAX((substring(contract_id FROM '^D([0-9]+)$'))::bigint)
                        FROM contracts
                        WHERE contract_id ~ '^D[0-9]+$'
                    ),
                    0
                ) + 1,
                1
            ),
            false
        )
        """
    )


def ensure_application_subject_schema(cur):
    """Добавляет предмет по РД в строки заявки, если база была создана раньше."""
    cur.execute(
        """
        ALTER TABLE purchase_application_items
        ADD COLUMN IF NOT EXISTS work_doc_subject text
        """
    )


def next_contract_id(cur):
    # Последовательность в старых базах могла отстать от уже созданных DXXXXXX.
    while True:
        cur.execute("SELECT nextval('contract_seq') AS n")
        number = cur.fetchone()["n"]
        candidate = f"D{number:06d}"
        cur.execute("SELECT 1 FROM contracts WHERE contract_id = %s", (candidate,))
        if not cur.fetchone():
            return candidate


def validate_work_doc_rows(cur, items):
    """
    Проверяет, что в каждой строке заявки заполнена пара
    Шифр РД + выбранный предмет по РД и эта пара есть в справочнике.
    """
    cur.execute(
        """
        SELECT work_doc_code, work_doc_subject
        FROM work_document_subjects
        """
    )

    known_pairs = {
        (normalize_work_doc(row["work_doc_code"]), normalize_key(row["work_doc_subject"]))
        for row in cur.fetchall()
        if row.get("work_doc_code") and row.get("work_doc_subject")
    }

    missing = []

    for item in items:
        code = normalize_work_doc(item.get("work_doc_code"))
        subject = normalize_text(item.get("work_doc_subject"))
        subject_key = normalize_key(subject)

        if not code or not subject_key:
            missing.append({
                "row": item.get("source_row_no"),
                "material_name": item.get("material_name"),
                "unit": item.get("unit"),
                "quantity": item.get("quantity"),
                "work_doc_code": item.get("work_doc_code"),
                "work_doc_subject": item.get("work_doc_subject"),
                "error": "В строке не заполнен шифр РД или предмет по РД",
            })
            continue

        if (code, subject_key) not in known_pairs:
            missing.append({
                "row": item.get("source_row_no"),
                "material_name": item.get("material_name"),
                "unit": item.get("unit"),
                "quantity": item.get("quantity"),
                "work_doc_code": item.get("work_doc_code"),
                "work_doc_subject": item.get("work_doc_subject"),
                "error": "Пара шифр РД / предмет по РД не найдена в справочнике",
            })

    return missing


def ensure_work_doc_subject_row(cur, work_doc_code, work_doc_subject, description=None):
    """Создаёт запись справочника РД без дублей по паре шифр + предмет."""
    code = normalize_work_doc(work_doc_code)
    subject = normalize_text(work_doc_subject)

    if not code:
        raise HTTPException(status_code=400, detail="Шифр РД обязателен")
    if not subject:
        raise HTTPException(status_code=400, detail="Предмет по РД обязателен")

    cur.execute(
        """
        SELECT work_doc_code, work_doc_subject, description
        FROM work_document_subjects
        WHERE lower(btrim(work_doc_code)) = lower(btrim(%s))
          AND lower(btrim(work_doc_subject)) = lower(btrim(%s))
        LIMIT 1
        """,
        (code, subject),
    )
    existing = cur.fetchone()

    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WORK_DOC_SUBJECT_DUPLICATE",
                "message": "Такая пара шифр РД / предмет по РД уже есть в справочнике.",
                "matches": [existing],
            },
        )

    cur.execute(
        """
        INSERT INTO work_document_subjects (
            work_doc_code,
            work_doc_subject,
            description,
            updated_at
        )
        VALUES (%s,%s,%s,now())
        RETURNING work_doc_code, work_doc_subject, description
        """,
        (code, subject, normalize_text(description)),
    )
    return cur.fetchone()
