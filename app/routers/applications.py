# import json
# import os
# from typing import Optional

# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel, Field

# from app.database import get_connection, fetch_all, fetch_one
# from app.services.material_okpd2 import ensure_material_okpd2_active_schema
# from app.services.suppliers import ensure_supplier_id_schema
# from app.services.units import ensure_unit_names_storage


# router = APIRouter()


# class RegistryFilters(BaseModel):
#     date_from: Optional[str] = None
#     date_to: Optional[str] = None
#     application_no: Optional[str] = None
#     construction_object: Optional[str] = None
#     material: Optional[str] = None
#     unit: Optional[str] = None
#     work_doc_code: Optional[str] = None
#     okpd2_code: Optional[str] = None
#     user_group_id: Optional[str] = None
#     supplier_search_method: Optional[str] = None
#     processing_status: Optional[str] = None
#     only_search_enabled: bool = False
#     item_ids: list[int] = Field(default_factory=list)

#     # ID конкретного запроса КП, например КП00001.
#     # Используется на шаге формирования черновиков, чтобы брать именно тот набор позиций,
#     # который был выбран при нажатии «Создать запрос КП».
#     kp_request_id: Optional[int] = None
#     kp_request_code: Optional[str] = None


# class RegistryItemUpdate(BaseModel):
#     supplier_search_method: Optional[str] = None
#     search_enabled: Optional[bool] = None


# def ensure_registry_columns(cur):
#     ensure_material_okpd2_active_schema(cur)
#     """Безопасно добавляет технические поля реестра, если база была создана до доработок."""
#     cur.execute(
#         """
#         ALTER TABLE purchase_application_items
#         ADD COLUMN IF NOT EXISTS add_to_search boolean DEFAULT false,
#         ADD COLUMN IF NOT EXISTS supplier_search_method text DEFAULT 'AI_SPARK',
#         ADD COLUMN IF NOT EXISTS processing_status text DEFAULT 'NEW',
#         ADD COLUMN IF NOT EXISTS work_doc_subject text,
#         ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now()
#         """
#     )

#     cur.execute(
#         """
#         ALTER TABLE purchase_applications
#         ADD COLUMN IF NOT EXISTS contract_id text,
#         ADD COLUMN IF NOT EXISTS contract_no text,
#         ADD COLUMN IF NOT EXISTS contract_date date,
#         ADD COLUMN IF NOT EXISTS contract_appendix text,
#         ADD COLUMN IF NOT EXISTS contract_subject text
#         """
#     )

#     cur.execute(
#         """
#         CREATE TABLE IF NOT EXISTS contracts (
#             contract_id text PRIMARY KEY,
#             contract_no text,
#             contract_date date,
#             contract_appendix text,
#             created_at timestamptz DEFAULT now() NOT NULL,
#             updated_at timestamptz DEFAULT now() NOT NULL
#         )
#         """
#     )
#     cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_no text")
#     cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_date date")
#     cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_appendix text")
#     cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now() NOT NULL")
#     cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now() NOT NULL")

#     cur.execute(
#         """
#         CREATE TABLE IF NOT EXISTS contract_work_doc_subjects (
#             contract_id text NOT NULL,
#             contract_appendix text NOT NULL DEFAULT '-',
#             work_doc_code text NOT NULL,
#             work_doc_subject text NOT NULL,
#             created_at timestamptz DEFAULT now() NOT NULL,
#             updated_at timestamptz DEFAULT now() NOT NULL
#         )
#         """
#     )
#     cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS contract_appendix text")
#     cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now() NOT NULL")
#     cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now() NOT NULL")
#     cur.execute("UPDATE contract_work_doc_subjects SET contract_appendix = '-' WHERE NULLIF(btrim(contract_appendix), '') IS NULL")

#     cur.execute(
#         """
#         ALTER TABLE purchase_application_items
#         ALTER COLUMN add_to_search SET DEFAULT false
#         """
#     )

#     cur.execute(
#         """
#         ALTER TABLE purchase_application_items
#         DROP CONSTRAINT IF EXISTS purchase_application_items_supplier_search_method_check
#         """
#     )

#     cur.execute(
#         """
#         UPDATE purchase_application_items
#         SET
#             add_to_search = COALESCE(add_to_search, false),
#             supplier_search_method = CASE
#                 WHEN supplier_search_method IN ('AI', 'SPARK', 'AI_SPARK') THEN supplier_search_method
#                 ELSE 'AI_SPARK'
#             END,
#             processing_status = COALESCE(NULLIF(processing_status, ''), 'NEW')
#         WHERE
#             add_to_search IS NULL
#             OR supplier_search_method IS NULL
#             OR supplier_search_method = ''
#             OR supplier_search_method NOT IN ('AI', 'SPARK', 'AI_SPARK')
#             OR processing_status IS NULL
#             OR processing_status = ''
#         """
#     )

#     cur.execute(
#         """
#         ALTER TABLE purchase_application_items
#         ADD CONSTRAINT purchase_application_items_supplier_search_method_check
#         CHECK (
#             supplier_search_method IS NULL
#             OR supplier_search_method IN ('AI', 'SPARK', 'AI_SPARK')
#         )
#         """
#     )


#     ensure_supplier_id_schema(cur)
#     ensure_unit_names_storage(cur)


# def ensure_kp_request_schema(cur):
#     """Создаёт таблицы и колонки для сущности запроса КП, например КП00001."""
#     cur.execute("CREATE SEQUENCE IF NOT EXISTS kp_request_seq START 1")

#     cur.execute(
#         """
#         CREATE TABLE IF NOT EXISTS kp_requests (
#             kp_request_id integer PRIMARY KEY DEFAULT nextval('kp_request_seq'),
#             kp_request_code text UNIQUE NOT NULL,
#             status text DEFAULT 'SUPPLIERS_SEARCHED',
#             filter_payload jsonb,
#             created_at timestamptz DEFAULT now(),
#             updated_at timestamptz DEFAULT now()
#         )
#         """
#     )

#     cur.execute(
#         """
#         CREATE TABLE IF NOT EXISTS kp_request_items (
#             kp_request_id integer NOT NULL REFERENCES kp_requests(kp_request_id) ON DELETE CASCADE,
#             item_id integer NOT NULL REFERENCES purchase_application_items(item_id) ON DELETE CASCADE,
#             PRIMARY KEY (kp_request_id, item_id)
#         )
#         """
#     )

#     cur.execute(
#         """
#         CREATE INDEX IF NOT EXISTS idx_kp_request_items_item_id
#         ON kp_request_items(item_id)
#         """
#     )

#     cur.execute(
#         """
#         ALTER TABLE supplier_search_results
#         ADD COLUMN IF NOT EXISTS kp_request_id integer,
#         ADD COLUMN IF NOT EXISTS kp_request_code text
#         """
#     )

#     cur.execute(
#         """
#         CREATE INDEX IF NOT EXISTS idx_supplier_search_results_kp_request_id
#         ON supplier_search_results(kp_request_id)
#         """
#     )

#     cur.execute(
#         """
#         ALTER TABLE procurement_email_batches
#         ADD COLUMN IF NOT EXISTS kp_request_id integer,
#         ADD COLUMN IF NOT EXISTS kp_request_code text
#         """
#     )

#     cur.execute(
#         """
#         CREATE INDEX IF NOT EXISTS idx_procurement_email_batches_kp_request_id
#         ON procurement_email_batches(kp_request_id)
#         """
#     )


# def create_kp_request(cur, item_ids: list[int], filter_payload: dict):
#     cur.execute("SELECT nextval('kp_request_seq') AS n")
#     number = cur.fetchone()["n"]
#     kp_request_code = f"КП{number:05d}"

#     cur.execute(
#         """
#         INSERT INTO kp_requests (
#             kp_request_id,
#             kp_request_code,
#             status,
#             filter_payload
#         )
#         VALUES (%s, %s, 'SUPPLIERS_SEARCHED', %s::jsonb)
#         RETURNING kp_request_id, kp_request_code
#         """,
#         (
#             number,
#             kp_request_code,
#             json.dumps(filter_payload, ensure_ascii=False, default=str),
#         ),
#     )
#     request = cur.fetchone()

#     cur.execute(
#         """
#         INSERT INTO kp_request_items (kp_request_id, item_id)
#         SELECT %s, unnest(%s::int[])
#         ON CONFLICT DO NOTHING
#         """,
#         (request["kp_request_id"], item_ids),
#     )

#     return request


# def resolve_kp_request(cur, filters: RegistryFilters):
#     if filters.kp_request_id:
#         cur.execute(
#             """
#             SELECT kp_request_id, kp_request_code
#             FROM kp_requests
#             WHERE kp_request_id = %s
#             """,
#             (filters.kp_request_id,),
#         )
#     elif filters.kp_request_code:
#         cur.execute(
#             """
#             SELECT kp_request_id, kp_request_code
#             FROM kp_requests
#             WHERE kp_request_code = %s
#             """,
#             (filters.kp_request_code,),
#         )
#     else:
#         return None

#     request = cur.fetchone()

#     if not request:
#         raise HTTPException(status_code=404, detail="КП-запрос не найден")

#     return request


# def resolve_kp_request_item_ids(cur, kp_request_id: int):
#     cur.execute(
#         """
#         SELECT item_id
#         FROM kp_request_items
#         WHERE kp_request_id = %s
#         ORDER BY item_id
#         """,
#         (kp_request_id,),
#     )
#     return [row["item_id"] for row in cur.fetchall()]




# def supplier_method_wants_spark(method: str) -> bool:
#     return (method or "AI_SPARK") in ("SPARK", "AI_SPARK")


# def supplier_method_wants_ai(method: str) -> bool:
#     return (method or "AI_SPARK") in ("AI", "AI_SPARK")


# def collect_supplier_mapping_issues(cur, item_ids: list[int]):
#     """Проверяет, достаточно ли связей для подбора поставщиков по выбранным позициям.

#     Для каждой позиции должен существовать хотя бы один полный маршрут, разрешённый
#     выбранным способом поиска:
#     - SPARK: Материал → ОКПД2 → ОКВЭД2 → Поставщик;
#     - AI: Материал → Группа материалов → Поставщик.

#     Если ни один разрешённый маршрут не полон, КП-запрос не создаём и возвращаем
#     пользователю список конкретных связей, которые нужно добавить в справочниках.
#     """
#     if not item_ids:
#         return {"can_create_kp": True, "missing_links": [], "blocked_items_count": 0}

#     cur.execute(
#         """
#         WITH selected_items AS (
#             SELECT
#                 i.item_id,
#                 i.material_id,
#                 i.material_name,
#                 COALESCE(i.supplier_search_method, 'AI_SPARK') AS supplier_search_method,
#                 NULLIF(btrim(i.okpd2_code_from_application), '') AS okpd2_from_application,
#                 NULLIF(btrim(i.user_group_id_from_application), '') AS user_group_from_application
#             FROM purchase_application_items i
#             WHERE i.item_id = ANY(%s)
#               AND i.add_to_search = true
#         ),
#         resolved AS (
#             SELECT
#                 si.*,
#                 COALESCE(si.okpd2_from_application, mom.okpd2_code) AS resolved_okpd2_code,
#                 COALESCE(si.user_group_from_application, mugm.id_possition) AS resolved_user_group_id
#             FROM selected_items si
#             LEFT JOIN material_okpd2_map mom
#                 ON btrim(mom.material_id) = btrim(si.material_id)
#                AND mom.is_active = true
#             LEFT JOIN material_user_group_map mugm
#                 ON btrim(mugm.material_id) = btrim(si.material_id)
#         ),
#         spark_stats AS (
#             SELECT
#                 r.item_id,
#                 EXISTS (
#                     SELECT 1
#                     FROM okpd2_okved2_map oom
#                     WHERE btrim(oom.okpd2_code) = btrim(r.resolved_okpd2_code)
#                 ) AS has_okpd2_okved2,
#                 EXISTS (
#                     SELECT 1
#                     FROM okpd2_okved2_map oom
#                     JOIN suppliers s
#                       ON btrim(s.okved2_code) = btrim(oom.okved2_code)
#                     WHERE btrim(oom.okpd2_code) = btrim(r.resolved_okpd2_code)
#                       AND s.inn IS NOT NULL
#                       AND btrim(s.inn) <> ''
#                 ) AS has_spark_supplier,
#                 (
#                     SELECT string_agg(DISTINCT oom.okved2_code, ', ' ORDER BY oom.okved2_code)
#                     FROM okpd2_okved2_map oom
#                     WHERE btrim(oom.okpd2_code) = btrim(r.resolved_okpd2_code)
#                 ) AS okved2_codes
#             FROM resolved r
#         ),
#         ai_stats AS (
#             SELECT
#                 r.item_id,
#                 EXISTS (
#                     SELECT 1
#                     FROM user_group_supply_map ugsm
#                     WHERE ugsm.user_group_id = r.resolved_user_group_id
#                       AND COALESCE(NULLIF(ugsm.supplier_id::text, ''), NULLIF(ugsm.inn_supply, '')) IS NOT NULL
#                 ) AS has_group_supplier_link,
#                 EXISTS (
#                     SELECT 1
#                     FROM user_group_supply_map ugsm
#                     LEFT JOIN suppliers s
#                       ON s.supplier_id::text = ugsm.supplier_id::text
#                       OR ((ugsm.supplier_id IS NULL OR btrim(ugsm.supplier_id::text) = '') AND btrim(s.inn) = btrim(ugsm.inn_supply))
#                     WHERE ugsm.user_group_id = r.resolved_user_group_id
#                       AND COALESCE(NULLIF(ugsm.supplier_id::text, ''), NULLIF(ugsm.inn_supply, '')) IS NOT NULL
#                       AND COALESCE(NULLIF(s.supplier_id::text, ''), NULLIF(s.inn, ''), NULLIF(ugsm.supplier_id::text, ''), NULLIF(ugsm.inn_supply, '')) IS NOT NULL
#                 ) AS has_ai_supplier
#             FROM resolved r
#         )
#         SELECT
#             r.item_id,
#             r.material_id,
#             r.material_name,
#             r.supplier_search_method,
#             r.resolved_okpd2_code,
#             r.resolved_user_group_id,
#             COALESCE(ss.has_okpd2_okved2, false) AS has_okpd2_okved2,
#             COALESCE(ss.has_spark_supplier, false) AS has_spark_supplier,
#             ss.okved2_codes,
#             COALESCE(ai.has_group_supplier_link, false) AS has_group_supplier_link,
#             COALESCE(ai.has_ai_supplier, false) AS has_ai_supplier
#         FROM resolved r
#         LEFT JOIN spark_stats ss ON ss.item_id = r.item_id
#         LEFT JOIN ai_stats ai ON ai.item_id = r.item_id
#         ORDER BY r.item_id
#         """,
#         (item_ids,),
#     )

#     rows = cur.fetchall()
#     missing_links = []
#     blocked_item_ids = set()

#     def add_issue(row, route, link_type, action, mapping_page, details=None):
#         missing_links.append({
#             "item_id": row.get("item_id"),
#             "material_id": row.get("material_id"),
#             "material_name": row.get("material_name"),
#             "supplier_search_method": row.get("supplier_search_method") or "AI_SPARK",
#             "route": route,
#             "missing_link_type": link_type,
#             "need_to_add": action,
#             "mapping_page": mapping_page,
#             "details": details or "",
#         })

#     for row in rows:
#         method = row.get("supplier_search_method") or "AI_SPARK"
#         wants_spark = supplier_method_wants_spark(method)
#         wants_ai = supplier_method_wants_ai(method)
#         spark_ok = False
#         ai_ok = False
#         item_issue_count_before = len(missing_links)

#         if wants_spark:
#             if not row.get("resolved_okpd2_code"):
#                 add_issue(
#                     row,
#                     "SPARK",
#                     "Материал → ОКПД2",
#                     "Добавьте активную связь материала с кодом ОКПД2",
#                     "Мэппинги → Материал → ОКПД2",
#                 )
#             elif not row.get("has_okpd2_okved2"):
#                 add_issue(
#                     row,
#                     "SPARK",
#                     "ОКПД2 → ОКВЭД2",
#                     "Добавьте связь ОКПД2 с ОКВЭД2",
#                     "Мэппинги → ОКПД2 → ОКВЭД2",
#                     f"ОКПД2: {row.get('resolved_okpd2_code')}",
#                 )
#             elif not row.get("has_spark_supplier"):
#                 add_issue(
#                     row,
#                     "SPARK",
#                     "ОКВЭД2 → Поставщик",
#                     "Добавьте поставщика с подходящим ОКВЭД2 в справочник поставщиков",
#                     "Справочники → Поставщики",
#                     f"ОКВЭД2: {row.get('okved2_codes') or 'не найден'}",
#                 )
#             else:
#                 spark_ok = True

#         if wants_ai:
#             if not row.get("resolved_user_group_id"):
#                 add_issue(
#                     row,
#                     "AI",
#                     "Материал → Группа материалов",
#                     "Добавьте связь материала с группой материалов",
#                     "Мэппинги → Материал → Группа",
#                 )
#             elif not row.get("has_group_supplier_link") or not row.get("has_ai_supplier"):
#                 add_issue(
#                     row,
#                     "AI",
#                     "Группа материалов → Поставщик",
#                     "Добавьте связь группы материалов с поставщиком",
#                     "Мэппинги → Группа → Поставщик",
#                     f"Группа: {row.get('resolved_user_group_id')}",
#                 )
#             else:
#                 ai_ok = True

#         has_allowed_route = (wants_spark and spark_ok) or (wants_ai and ai_ok)
#         if not has_allowed_route:
#             blocked_item_ids.add(row.get("item_id"))
#         else:
#             # Если маршрут хотя бы один рабочий, не блокируем КП. Удаляем предупреждения
#             # по запасному маршруту, чтобы пользователь видел только действительно критичные связи.
#             del missing_links[item_issue_count_before:]

#     return {
#         "can_create_kp": len(blocked_item_ids) == 0,
#         "missing_links": missing_links,
#         "blocked_items_count": len(blocked_item_ids),
#     }

# def build_registry_where(filters: RegistryFilters):
#     where = []
#     params = []

#     if filters.only_search_enabled:
#         where.append("i.add_to_search = true")

#     if filters.date_from:
#         where.append("(i.supply_end_date IS NULL OR i.supply_end_date >= %s)")
#         params.append(filters.date_from)

#     if filters.date_to:
#         where.append("(i.supply_start_date IS NULL OR i.supply_start_date <= %s)")
#         params.append(filters.date_to)

#     if filters.application_no:
#         where.append(
#             """
#             (
#                 lower(COALESCE(a.application_no, '')) LIKE lower(%s)
#                 OR a.application_id::text LIKE %s
#             )
#             """
#         )
#         params.extend([f"%{filters.application_no}%", f"%{filters.application_no}%"])

#     if filters.construction_object:
#         where.append("lower(COALESCE(a.construction_object, '')) LIKE lower(%s)")
#         params.append(f"%{filters.construction_object}%")

#     if filters.material:
#         where.append(
#             """
#             (
#                 lower(COALESCE(i.material_name, '')) LIKE lower(%s)
#                 OR lower(COALESCE(i.material_id, '')) LIKE lower(%s)
#             )
#             """
#         )
#         params.extend([f"%{filters.material}%", f"%{filters.material}%"])

#     if filters.unit:
#         where.append(
#             """
#             (
#                 lower(COALESCE(i.unit, '')) LIKE lower(%s)
#                 OR lower(COALESCE(u.unit_name, '')) LIKE lower(%s)
#                 OR lower(COALESCE(u.unit_code, '')) LIKE lower(%s)
#             )
#             """
#         )
#         params.extend([f"%{filters.unit}%", f"%{filters.unit}%", f"%{filters.unit}%"])

#     if filters.work_doc_code:
#         where.append("lower(COALESCE(i.work_doc_code, '')) LIKE lower(%s)")
#         params.append(f"%{filters.work_doc_code}%")

#     if filters.okpd2_code:
#         where.append("btrim(COALESCE(mom.okpd2_code, '')) = btrim(%s)")
#         params.append(filters.okpd2_code)

#     if filters.user_group_id:
#         where.append("COALESCE(i.user_group_id_from_application, mugm.id_possition) = %s")
#         params.append(filters.user_group_id)

#     if filters.supplier_search_method:
#         where.append("COALESCE(i.supplier_search_method, 'AI_SPARK') = %s")
#         params.append(filters.supplier_search_method)

#     if filters.processing_status:
#         where.append("i.processing_status = %s")
#         params.append(filters.processing_status)

#     where_sql = "WHERE " + " AND ".join(where) if where else ""
#     return where_sql, params


# def resolve_registry_item_ids(cur, filters: RegistryFilters):
#     if filters.item_ids:
#         item_ids = list(dict.fromkeys(int(item_id) for item_id in filters.item_ids if item_id))
#     else:
#         where_sql, params = build_registry_where(filters)
#         cur.execute(
#             f"""
#             SELECT i.item_id
#             FROM purchase_application_items i
#             JOIN purchase_applications a
#                 ON a.application_id = i.application_id
#             LEFT JOIN material_okpd2_map mom
#                 ON trim(mom.material_id) = trim(i.material_id)
#             AND mom.is_active = true
#             LEFT JOIN material_user_group_map mugm
#                 ON trim(mugm.material_id) = trim(i.material_id)
#             LEFT JOIN units u
#                 ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
#                 OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
#             {where_sql}
#             """,
#             tuple(params),
#         )
#         item_ids = [row["item_id"] for row in cur.fetchall()]

#     if not item_ids:
#         return []

#     cur.execute(
#         """
#         SELECT item_id
#         FROM purchase_application_items
#         WHERE item_id = ANY(%s)
#           AND add_to_search = true
#         ORDER BY item_id
#         """,
#         (item_ids,),
#     )
#     return [row["item_id"] for row in cur.fetchall()]


# def run_supplier_search(cur, item_ids: list[int], kp_request_id: int, kp_request_code: str):
#     cur.execute(
#         """
#         DELETE FROM supplier_search_results
#         WHERE kp_request_id = %s
#         """,
#         (kp_request_id,),
#     )

#     # SPARK: Material → OKPD2 → OKVED2 → suppliers
#     cur.execute(
#         """
#         INSERT INTO supplier_search_results (
#             kp_request_id,
#             kp_request_code,
#             item_id,
#             supplier_id,
#             search_method,
#             source_system,
#             material_id,
#             okpd2_code,
#             okved2_code,
#             user_group_id,
#             supplier_inn,
#             supplier_name,
#             match_reason
#         )
#         SELECT DISTINCT
#             %s AS kp_request_id,
#             %s AS kp_request_code,
#             i.item_id,
#             sr.supplier_id,
#             'SPARK' AS search_method,
#             'SPARK' AS source_system,
#             trim(i.material_id) AS material_id,
#             trim(COALESCE(i.okpd2_code_from_application, mom.okpd2_code)) AS okpd2_code,
#             trim(oom.okved2_code) AS okved2_code,
#             NULL::text AS user_group_id,
#             trim(sr.inn) AS supplier_inn,
#             sr.name AS supplier_name,
#             'Реестр: Material → OKPD2 → OKVED2 → suppliers / SPARK'
#         FROM purchase_application_items i
#         LEFT JOIN material_okpd2_map mom
#             ON trim(mom.material_id) = trim(i.material_id)
#         AND mom.is_active = true
#         JOIN okpd2_okved2_map oom
#             ON trim(oom.okpd2_code) = trim(COALESCE(i.okpd2_code_from_application, mom.okpd2_code))
#         JOIN suppliers sr
#             ON trim(sr.okved2_code) = trim(oom.okved2_code)
#         WHERE i.item_id = ANY(%s)
#           AND i.add_to_search = true
#           AND COALESCE(i.supplier_search_method, 'AI_SPARK') IN ('SPARK', 'AI_SPARK')
#           AND i.material_id IS NOT NULL
#           AND trim(i.material_id) <> ''
#           AND COALESCE(i.okpd2_code_from_application, mom.okpd2_code) IS NOT NULL
#           AND trim(COALESCE(i.okpd2_code_from_application, mom.okpd2_code)) <> ''
#           AND sr.inn IS NOT NULL
#           AND trim(sr.inn) <> ''
#         """,
#         (kp_request_id, kp_request_code, item_ids),
#     )

#     # AI: Material → Group → suppliers
#     cur.execute(
#         """
#         INSERT INTO supplier_search_results (
#             kp_request_id,
#             kp_request_code,
#             item_id,
#             supplier_id,
#             search_method,
#             source_system,
#             material_id,
#             okpd2_code,
#             okved2_code,
#             user_group_id,
#             supplier_inn,
#             supplier_name,
#             match_reason
#         )
#         SELECT DISTINCT
#             %s AS kp_request_id,
#             %s AS kp_request_code,
#             i.item_id,
#             COALESCE(ugsm.supplier_id::text, s.supplier_id::text) AS supplier_id,
#             'AI' AS search_method,
#             'AI' AS source_system,
#             i.material_id,
#             NULL::text AS okpd2_code,
#             NULL::text AS okved2_code,
#             COALESCE(i.user_group_id_from_application, mugm.id_possition) AS user_group_id,
#             COALESCE(s.inn, ugsm.inn_supply) AS supplier_inn,
#             COALESCE(NULLIF(s.name, ''), NULLIF(ugsm.supplier_id::text, ''), NULLIF(ugsm.inn_supply, ''), 'Не найдено') AS supplier_name,
#             'Реестр: Material → Group → user_group_supply_map / suppliers'
#         FROM purchase_application_items i
#         LEFT JOIN material_user_group_map mugm
#             ON trim(mugm.material_id) = trim(i.material_id)
#         JOIN user_group_supply_map ugsm
#             ON ugsm.user_group_id = COALESCE(i.user_group_id_from_application, mugm.id_possition)
#         LEFT JOIN suppliers s
#             ON s.supplier_id::text = ugsm.supplier_id::text
#             OR ((ugsm.supplier_id IS NULL OR btrim(ugsm.supplier_id::text) = '') AND btrim(s.inn) = btrim(ugsm.inn_supply))
#         WHERE i.item_id = ANY(%s)
#           AND i.add_to_search = true
#           AND COALESCE(i.supplier_search_method, 'AI_SPARK') IN ('AI', 'AI_SPARK')
#           AND COALESCE(i.user_group_id_from_application, mugm.id_possition) IS NOT NULL
#           AND COALESCE(NULLIF(ugsm.supplier_id::text, ''), NULLIF(ugsm.inn_supply, '')) IS NOT NULL
#         """,
#         (kp_request_id, kp_request_code, item_ids),
#     )

#     cur.execute(
#         """
#         SELECT COUNT(*) AS cnt
#         FROM supplier_search_results
#         WHERE kp_request_id = %s
#           AND item_id = ANY(%s)
#         """,
#         (kp_request_id, item_ids),
#     )
#     supplier_results_count = cur.fetchone()["cnt"]

#     if supplier_results_count == 0:
#         cur.execute(
#             """
#             UPDATE purchase_application_items
#             SET processing_status = 'NO_SUPPLIERS',
#                 updated_at = now()
#             WHERE item_id = ANY(%s)
#             """,
#             (item_ids,),
#         )
#         cur.execute(
#             """
#             UPDATE kp_requests
#             SET status = 'NO_SUPPLIERS',
#                 updated_at = now()
#             WHERE kp_request_id = %s
#             """,
#             (kp_request_id,),
#         )
#     else:
#         cur.execute(
#             """
#             UPDATE purchase_application_items i
#             SET processing_status = 'SUPPLIERS_FOUND',
#                 updated_at = now()
#             WHERE i.item_id = ANY(%s)
#               AND EXISTS (
#                   SELECT 1
#                   FROM supplier_search_results r
#                   WHERE r.kp_request_id = %s
#                     AND r.item_id = i.item_id
#               )
#             """,
#             (item_ids, kp_request_id),
#         )

#         cur.execute(
#             """
#             UPDATE purchase_application_items i
#             SET processing_status = 'NO_SUPPLIERS',
#                 updated_at = now()
#             WHERE i.item_id = ANY(%s)
#               AND NOT EXISTS (
#                   SELECT 1
#                   FROM supplier_search_results r
#                   WHERE r.kp_request_id = %s
#                     AND r.item_id = i.item_id
#               )
#             """,
#             (item_ids, kp_request_id),
#         )

#     return supplier_results_count


# def create_email_batches_from_results(
#     cur,
#     item_ids: list[int],
#     filter_payload: dict,
#     kp_request_id: Optional[int] = None,
#     kp_request_code: Optional[str] = None,
# ):
#     if kp_request_id:
#         cur.execute(
#             """
#             DELETE FROM procurement_email_batches
#             WHERE kp_request_id = %s
#             """,
#             (kp_request_id,),
#         )

#     cur.execute(
#         """
#         SELECT COUNT(*) AS cnt
#         FROM supplier_search_results r
#         WHERE r.item_id = ANY(%s)
#           AND (%s IS NULL OR r.kp_request_id = %s)
#         """,
#         (item_ids, kp_request_id, kp_request_id),
#     )
#     supplier_results_count = cur.fetchone()["cnt"]

#     if supplier_results_count == 0:
#         return 0, [], 0

#     cur.execute(
#         """
#         SELECT
#             r.supplier_id,
#             r.supplier_inn,
#             r.supplier_name,
#             r.search_method,
#             r.okpd2_code,
#             r.okved2_code,
#             r.user_group_id,
#             MIN(i.supply_start_date) AS supply_start_date,
#             MAX(i.supply_end_date) AS supply_end_date,
#             COUNT(DISTINCT r.item_id) AS items_count
#         FROM supplier_search_results r
#         JOIN purchase_application_items i
#             ON i.item_id = r.item_id
#         WHERE r.item_id = ANY(%s)
#           AND (%s IS NULL OR r.kp_request_id = %s)
#         GROUP BY
#             r.supplier_id,
#             r.supplier_inn,
#             r.supplier_name,
#             r.search_method,
#             r.okpd2_code,
#             r.okved2_code,
#             r.user_group_id
#         HAVING COUNT(DISTINCT r.item_id) > 0
#         """,
#         (item_ids, kp_request_id, kp_request_id),
#     )

#     groups = cur.fetchall()
#     created_batches = 0
#     batch_ids = []

#     for group in groups:
#         if not group["supplier_id"] and not group["supplier_inn"] and not group["supplier_name"]:
#             continue

#         cur.execute(
#             """
#             INSERT INTO procurement_email_batches (
#                 kp_request_id,
#                 kp_request_code,
#                 application_id,
#                 supplier_id,
#                 supplier_inn,
#                 supplier_name,
#                 search_method,
#                 okpd2_code,
#                 okved2_code,
#                 user_group_id,
#                 supply_start_date,
#                 supply_end_date,
#                 status,
#                 source_mode,
#                 filter_payload
#             )
#             VALUES (
#                 %s,
#                 %s,
#                 NULL,
#                 %s,
#                 %s,
#                 %s,
#                 %s,
#                 %s,
#                 %s,
#                 %s,
#                 %s,
#                 %s,
#                 'DRAFT',
#                 'REGISTRY',
#                 %s::jsonb
#             )
#             RETURNING batch_id
#             """,
#             (
#                 kp_request_id,
#                 kp_request_code,
#                 group["supplier_id"],
#                 group["supplier_inn"],
#                 group["supplier_name"],
#                 group["search_method"],
#                 group["okpd2_code"],
#                 group["okved2_code"],
#                 group["user_group_id"],
#                 group["supply_start_date"],
#                 group["supply_end_date"],
#                 json.dumps(filter_payload, ensure_ascii=False, default=str),
#             ),
#         )

#         batch_id = cur.fetchone()["batch_id"]

#         cur.execute(
#             """
#             INSERT INTO procurement_email_batch_items (batch_id, item_id)
#             SELECT DISTINCT
#                 %s,
#                 r.item_id
#             FROM supplier_search_results r
#             WHERE r.item_id = ANY(%s)
#               AND (%s IS NULL OR r.kp_request_id = %s)
#               AND COALESCE(r.supplier_id::text, '') = COALESCE(%s::text, '')
#               AND COALESCE(r.supplier_inn, '') = COALESCE(%s, '')
#               AND COALESCE(r.supplier_name, '') = COALESCE(%s, '')
#               AND r.search_method = %s
#               AND COALESCE(r.okpd2_code, '') = COALESCE(%s, '')
#               AND COALESCE(r.okved2_code, '') = COALESCE(%s, '')
#               AND COALESCE(r.user_group_id, '') = COALESCE(%s, '')
#             """,
#             (
#                 batch_id,
#                 item_ids,
#                 kp_request_id,
#                 kp_request_id,
#                 group["supplier_id"],
#                 group["supplier_inn"],
#                 group["supplier_name"],
#                 group["search_method"],
#                 group["okpd2_code"],
#                 group["okved2_code"],
#                 group["user_group_id"],
#             ),
#         )

#         cur.execute(
#             """
#             SELECT COUNT(*) AS cnt
#             FROM procurement_email_batch_items
#             WHERE batch_id = %s
#             """,
#             (batch_id,),
#         )

#         batch_items_count = cur.fetchone()["cnt"]

#         if batch_items_count == 0:
#             cur.execute(
#                 """
#                 DELETE FROM procurement_email_batches
#                 WHERE batch_id = %s
#                 """,
#                 (batch_id,),
#             )
#         else:
#             created_batches += 1
#             batch_ids.append(batch_id)

#     if created_batches:
#         cur.execute(
#             """
#             UPDATE purchase_application_items
#             SET processing_status = 'EMAIL_PREPARED',
#                 updated_at = now()
#             WHERE item_id IN (
#                 SELECT item_id
#                 FROM procurement_email_batch_items
#                 WHERE batch_id = ANY(%s)
#             )
#             """,
#             (batch_ids,),
#         )

#         if kp_request_id:
#             cur.execute(
#                 """
#                 UPDATE kp_requests
#                 SET status = 'EMAIL_PREPARED',
#                     updated_at = now()
#                 WHERE kp_request_id = %s
#                 """,
#                 (kp_request_id,),
#             )

#     return created_batches, batch_ids, supplier_results_count


# @router.get("/")
# def get_applications():
#     """Возвращает реестр заявок и не теряет legacy-заявки после миграций.

#     В старых БД часть заявок могла быть создана до появления новых полей договора
#     или даже без полноценной строки в purchase_applications. Поэтому перед чтением
#     синхронизируем схему, а список строим от фактических позиций тоже.
#     """
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_registry_columns(cur)
#             ensure_kp_request_schema(cur)
#             conn.commit()

#     return fetch_all(
#         """
#         WITH item_stats AS (
#             SELECT
#                 application_id,
#                 COUNT(*) AS items_count
#             FROM purchase_application_items
#             GROUP BY application_id
#         ),
#         application_rows AS (
#             SELECT
#                 a.application_id,
#                 COALESCE(NULLIF(a.application_no, ''), 'Заявка №' || a.application_id::text) AS application_no,
#                 a.application_date,
#                 a.construction_object,
#                 a.source_file_name,
#                 COALESCE(a.created_at, a.application_date::timestamptz) AS created_at,
#                 COALESCE(s.items_count, 0) AS items_count
#             FROM purchase_applications a
#             LEFT JOIN item_stats s
#                 ON s.application_id = a.application_id

#             UNION ALL

#             SELECT
#                 s.application_id,
#                 'Заявка №' || s.application_id::text AS application_no,
#                 NULL::date AS application_date,
#                 NULL::text AS construction_object,
#                 NULL::text AS source_file_name,
#                 NULL::timestamptz AS created_at,
#                 s.items_count
#             FROM item_stats s
#             LEFT JOIN purchase_applications a
#                 ON a.application_id = s.application_id
#             WHERE a.application_id IS NULL
#         )
#         SELECT *
#         FROM application_rows
#         ORDER BY created_at DESC NULLS LAST, application_id DESC
#         """
#     )

# def remove_uploaded_source_file(source_file_path: Optional[str]):
#     """Удаляет исходный Excel-файл заявки только из локальной папки uploads."""
#     if not source_file_path or source_file_path == "manual_input":
#         return False

#     uploads_dir = os.path.abspath("uploads")
#     file_path = os.path.abspath(source_file_path)

#     try:
#         if os.path.commonpath([uploads_dir, file_path]) != uploads_dir:
#             return False

#         if os.path.isfile(file_path):
#             os.remove(file_path)
#             return True
#     except Exception:
#         return False

#     return False

# @router.delete("/{application_id}")
# def delete_application(application_id: int):
#     """Удаляет заявку и все связанные с ней позиции/материалы из рабочих реестров."""
#     conn = get_connection()
#     source_file_path = None

#     try:
#         with conn:
#             with conn.cursor() as cur:
#                 ensure_registry_columns(cur)
#                 ensure_kp_request_schema(cur)

#                 cur.execute(
#                     """
#                     SELECT application_id, application_no, source_file_path
#                     FROM purchase_applications
#                     WHERE application_id = %s
#                     """,
#                     (application_id,),
#                 )
#                 application = cur.fetchone()

#                 if not application:
#                     raise HTTPException(status_code=404, detail="Заявка не найдена")

#                 source_file_path = application.get("source_file_path")

#                 cur.execute(
#                     """
#                     SELECT item_id
#                     FROM purchase_application_items
#                     WHERE application_id = %s
#                     """,
#                     (application_id,),
#                 )
#                 item_ids = [row["item_id"] for row in cur.fetchall()]

#                 touched_batch_ids = []
#                 application_batch_ids = []
#                 touched_kp_request_ids = []
#                 deleted_batch_item_links = 0
#                 deleted_supplier_results = 0
#                 deleted_kp_item_links = 0
#                 deleted_items = 0
#                 deleted_batches = 0
#                 deleted_kp_requests = 0

#                 if item_ids:
#                     cur.execute(
#                         """
#                         SELECT DISTINCT batch_id
#                         FROM procurement_email_batch_items
#                         WHERE item_id = ANY(%s)
#                         """,
#                         (item_ids,),
#                     )
#                     touched_batch_ids = [row["batch_id"] for row in cur.fetchall()]

#                     cur.execute(
#                         """
#                         SELECT DISTINCT kp_request_id
#                         FROM kp_request_items
#                         WHERE item_id = ANY(%s)
#                         """,
#                         (item_ids,),
#                     )
#                     touched_kp_request_ids = [
#                         row["kp_request_id"]
#                         for row in cur.fetchall()
#                         if row.get("kp_request_id")
#                     ]

#                 cur.execute(
#                     """
#                     SELECT batch_id
#                     FROM procurement_email_batches
#                     WHERE application_id = %s
#                     """,
#                     (application_id,),
#                 )
#                 application_batch_ids = [row["batch_id"] for row in cur.fetchall()]

#                 all_known_batch_ids = list(dict.fromkeys(touched_batch_ids + application_batch_ids))

#                 if application_batch_ids:
#                     cur.execute(
#                         """
#                         DELETE FROM procurement_email_batch_items
#                         WHERE batch_id = ANY(%s)
#                         """,
#                         (application_batch_ids,),
#                     )
#                     deleted_batch_item_links += cur.rowcount or 0

#                 if item_ids:
#                     cur.execute(
#                         """
#                         DELETE FROM procurement_email_batch_items
#                         WHERE item_id = ANY(%s)
#                         """,
#                         (item_ids,),
#                     )
#                     deleted_batch_item_links += cur.rowcount or 0

#                     cur.execute(
#                         """
#                         DELETE FROM supplier_search_results
#                         WHERE item_id = ANY(%s)
#                         """,
#                         (item_ids,),
#                     )
#                     deleted_supplier_results = cur.rowcount or 0

#                     cur.execute(
#                         """
#                         DELETE FROM kp_request_items
#                         WHERE item_id = ANY(%s)
#                         """,
#                         (item_ids,),
#                     )
#                     deleted_kp_item_links = cur.rowcount or 0

#                     cur.execute(
#                         """
#                         DELETE FROM purchase_application_items
#                         WHERE application_id = %s
#                         """,
#                         (application_id,),
#                     )
#                     deleted_items = cur.rowcount or 0

#                 if all_known_batch_ids:
#                     cur.execute(
#                         """
#                         DELETE FROM procurement_email_batches b
#                         WHERE b.application_id = %s
#                            OR (
#                                 b.batch_id = ANY(%s)
#                                 AND NOT EXISTS (
#                                     SELECT 1
#                                     FROM procurement_email_batch_items bi
#                                     WHERE bi.batch_id = b.batch_id
#                                 )
#                            )
#                         """,
#                         (application_id, all_known_batch_ids),
#                     )
#                     deleted_batches = cur.rowcount or 0
#                 else:
#                     cur.execute(
#                         """
#                         DELETE FROM procurement_email_batches
#                         WHERE application_id = %s
#                         """,
#                         (application_id,),
#                     )
#                     deleted_batches = cur.rowcount or 0

#                 if touched_kp_request_ids:
#                     cur.execute(
#                         """
#                         DELETE FROM kp_requests kr
#                         WHERE kr.kp_request_id = ANY(%s)
#                           AND NOT EXISTS (
#                               SELECT 1
#                               FROM kp_request_items kri
#                               WHERE kri.kp_request_id = kr.kp_request_id
#                           )
#                         """,
#                         (touched_kp_request_ids,),
#                     )
#                     deleted_kp_requests = cur.rowcount or 0

#                     cur.execute(
#                         """
#                         UPDATE kp_requests kr
#                         SET status = CASE
#                                 WHEN COALESCE(stats.total_batches, 0) = 0 THEN kr.status
#                                 WHEN stats.sent_batches = stats.total_batches THEN 'EMAIL_SENT'
#                                 WHEN stats.sent_batches > 0 THEN 'PARTIALLY_SENT'
#                                 WHEN stats.error_batches > 0 THEN 'SEND_ERROR'
#                                 ELSE 'EMAIL_PREPARED'
#                             END,
#                             updated_at = now()
#                         FROM (
#                             SELECT
#                                 kp_request_id,
#                                 COUNT(*) AS total_batches,
#                                 COUNT(*) FILTER (WHERE status = 'SENT') AS sent_batches,
#                                 COUNT(*) FILTER (WHERE status = 'SEND_ERROR') AS error_batches
#                             FROM procurement_email_batches
#                             WHERE kp_request_id = ANY(%s)
#                             GROUP BY kp_request_id
#                         ) stats
#                         WHERE kr.kp_request_id = stats.kp_request_id
#                         """,
#                         (touched_kp_request_ids,),
#                     )

#                 cur.execute(
#                     """
#                     DELETE FROM purchase_applications
#                     WHERE application_id = %s
#                     """,
#                     (application_id,),
#                 )

#                 return_payload = {
#                     "status": "OK",
#                     "application_id": application_id,
#                     "application_no": application.get("application_no"),
#                     "deleted_items_count": deleted_items,
#                     "deleted_supplier_results_count": deleted_supplier_results,
#                     "deleted_kp_item_links_count": deleted_kp_item_links,
#                     "deleted_batch_item_links_count": deleted_batch_item_links,
#                     "deleted_batches_count": deleted_batches,
#                     "deleted_empty_kp_requests_count": deleted_kp_requests,
#                 }

#         return_payload["source_file_deleted"] = remove_uploaded_source_file(source_file_path)
#         return return_payload

#     except HTTPException:
#         raise
#     except Exception as error:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Ошибка удаления заявки: {str(error)}",
#         )
#     finally:
#         conn.close()



# @router.get("/registry")
# def get_registry(
#     date_from: Optional[str] = None,
#     date_to: Optional[str] = None,
#     application_no: Optional[str] = None,
#     construction_object: Optional[str] = None,
#     material: Optional[str] = None,
#     unit: Optional[str] = None,
#     work_doc_code: Optional[str] = None,
#     okpd2_code: Optional[str] = None,
#     user_group_id: Optional[str] = None,
#     supplier_search_method: Optional[str] = None,
#     processing_status: Optional[str] = None,
#     only_search_enabled: bool = False,
# ):
#     filters = RegistryFilters(
#         date_from=date_from,
#         date_to=date_to,
#         application_no=application_no,
#         construction_object=construction_object,
#         material=material,
#         unit=unit,
#         work_doc_code=work_doc_code,
#         okpd2_code=okpd2_code,
#         user_group_id=user_group_id,
#         supplier_search_method=supplier_search_method,
#         processing_status=processing_status,
#         only_search_enabled=only_search_enabled,
#     )

#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_registry_columns(cur)
#             ensure_kp_request_schema(cur)
#             conn.commit()

#     where_sql, params = build_registry_where(filters)

#     return fetch_all(
#         f"""
#         SELECT
#             a.application_id,
#             a.application_no,
#             a.application_date,
#             a.construction_object,
#             COALESCE(NULLIF(a.contract_no, ''), contract_base.contract_no, contract_link.contract_no) AS contract_no,
#             COALESCE(a.contract_date::text, contract_base.contract_date::text, contract_link.contract_date) AS contract_date,
#             COALESCE(NULLIF(contract_link.contract_appendix, ''), NULLIF(a.contract_appendix, '')) AS contract_appendix,

#             i.item_id,
#             i.material_id,

#             COALESCE(i.okpd2_code_from_application, mom.okpd2_code) AS okpd2_code,
#             COALESCE(i.user_group_id_from_application, mugm.id_possition) AS user_group_id,

#             i.material_name,
#             COALESCE(u.unit_name, i.unit) AS unit,
#             i.quantity,
#             i.characteristics_comment,
#             i.work_doc_code,
#             COALESCE(NULLIF(i.work_doc_subject, ''), contract_link.work_doc_subject) AS work_doc_subject,
#             i.supply_start_date,
#             i.supply_end_date,

#             COALESCE(i.supplier_search_method, 'AI_SPARK') AS supplier_search_method,
#             COALESCE(i.add_to_search, false) AS search_enabled,
#             COALESCE(i.processing_status, 'NEW') AS processing_status,

#             CASE
#                 WHEN i.supply_start_date IS NOT NULL AND i.supply_end_date IS NOT NULL
#                     THEN i.supply_start_date::text || ' — ' || i.supply_end_date::text
#                 WHEN i.supply_start_date IS NOT NULL
#                     THEN i.supply_start_date::text
#                 WHEN i.supply_end_date IS NOT NULL
#                     THEN i.supply_end_date::text
#                 ELSE NULL
#             END AS supply_period
#         FROM purchase_application_items i
#         JOIN purchase_applications a
#             ON a.application_id = i.application_id
#         LEFT JOIN material_okpd2_map mom
#             ON trim(mom.material_id) = trim(i.material_id)
#         AND mom.is_active = true
#         LEFT JOIN material_user_group_map mugm
#             ON trim(mugm.material_id) = trim(i.material_id)
#         LEFT JOIN contracts contract_base
#             ON contract_base.contract_id = a.contract_id
#         LEFT JOIN LATERAL (
#             SELECT
#                 string_agg(DISTINCT c.contract_no, ', ' ORDER BY c.contract_no) AS contract_no,
#                 string_agg(DISTINCT c.contract_date::text, ', ' ORDER BY c.contract_date::text) FILTER (WHERE c.contract_date IS NOT NULL) AS contract_date,
#                 string_agg(DISTINCT l.contract_appendix, ', ' ORDER BY l.contract_appendix) AS contract_appendix,
#                 string_agg(DISTINCT l.work_doc_subject, ', ' ORDER BY l.work_doc_subject) AS work_doc_subject
#             FROM contract_work_doc_subjects l
#             JOIN contracts c
#                 ON c.contract_id = l.contract_id
#             WHERE (NULLIF(btrim(a.contract_id), '') IS NULL OR l.contract_id = a.contract_id)
#               AND lower(btrim(l.work_doc_code)) = lower(btrim(i.work_doc_code))
#               AND (
#                     NULLIF(btrim(i.work_doc_subject), '') IS NULL
#                     OR lower(btrim(l.work_doc_subject)) = lower(btrim(i.work_doc_subject))
#                   )
#         ) contract_link ON true
#         LEFT JOIN units u
#             ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
#             OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
#         {where_sql}
#         ORDER BY
#             COALESCE(i.supply_start_date, a.application_date) NULLS LAST,
#             a.application_id DESC,
#             i.source_row_no NULLS LAST,
#             i.item_id
#         """,
#         tuple(params),
#     )


# @router.patch("/registry/items/{item_id}")
# def update_registry_item(item_id: int, payload: RegistryItemUpdate):
#     allowed_methods = {"AI", "SPARK", "AI_SPARK"}

#     if payload.supplier_search_method and payload.supplier_search_method not in allowed_methods:
#         raise HTTPException(
#             status_code=400,
#             detail="Способ поиска должен быть AI, SPARK или AI_SPARK",
#         )

#     conn = get_connection()

#     try:
#         with conn:
#             with conn.cursor() as cur:
#                 ensure_registry_columns(cur)

#                 cur.execute(
#                     """
#                     UPDATE purchase_application_items
#                     SET
#                         supplier_search_method = COALESCE(%s, supplier_search_method),
#                         add_to_search = COALESCE(%s, add_to_search),
#                         updated_at = now()
#                     WHERE item_id = %s
#                     RETURNING
#                         item_id,
#                         supplier_search_method,
#                         add_to_search AS search_enabled,
#                         processing_status
#                     """,
#                     (
#                         payload.supplier_search_method,
#                         payload.search_enabled,
#                         item_id,
#                     ),
#                 )

#                 updated = cur.fetchone()

#                 if not updated:
#                     raise HTTPException(status_code=404, detail="Позиция не найдена")

#                 return {"status": "OK", "item": updated}

#     finally:
#         conn.close()


# @router.post("/registry/search-suppliers")
# def search_registry_suppliers(filters: RegistryFilters):
#     filter_payload = filters.dict()
#     conn = get_connection()

#     try:
#         with conn:
#             with conn.cursor() as cur:
#                 ensure_registry_columns(cur)
#                 ensure_kp_request_schema(cur)
#                 item_ids = resolve_registry_item_ids(cur, filters)

#                 if not item_ids:
#                     return {
#                         "status": "NO_SELECTED_ITEMS",
#                         "message": "Нет позиций, отмеченных для участия в отборе.",
#                         "items_count": 0,
#                         "supplier_results_count": 0,
#                         "kp_request_id": None,
#                         "kp_request_code": None,
#                     }

#                 readiness = collect_supplier_mapping_issues(cur, item_ids)

#                 if not readiness["can_create_kp"]:
#                     return {
#                         "status": "MAPPINGS_REQUIRED",
#                         "message": (
#                             "По выбранным позициям нельзя создать запрос КП: не хватает связей в справочниках. "
#                             "Проверьте мэппинги и добавьте связи из списка ниже."
#                         ),
#                         "items_count": len(item_ids),
#                         "blocked_items_count": readiness["blocked_items_count"],
#                         "supplier_results_count": 0,
#                         "filter_payload": filter_payload,
#                         "kp_request_id": None,
#                         "kp_request_code": None,
#                         "missing_links": readiness["missing_links"],
#                     }

#                 kp_request = create_kp_request(cur, item_ids, filter_payload)

#                 supplier_results_count = run_supplier_search(
#                     cur,
#                     item_ids,
#                     kp_request["kp_request_id"],
#                     kp_request["kp_request_code"],
#                 )

#                 return {
#                     "status": "OK" if supplier_results_count else "NO_SUPPLIERS",
#                     "message": "Подбор поставщиков завершён." if supplier_results_count else "По выбранным позициям поставщики не найдены.",
#                     "items_count": len(item_ids),
#                     "blocked_items_count": 0,
#                     "supplier_results_count": supplier_results_count,
#                     "filter_payload": filter_payload,
#                     "kp_request_id": kp_request["kp_request_id"],
#                     "kp_request_code": kp_request["kp_request_code"],
#                     "missing_links": [],
#                 }

#     except HTTPException:
#         raise
#     except Exception as error:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Ошибка подбора поставщиков по реестру: {str(error)}",
#         )
#     finally:
#         conn.close()


# @router.post("/registry/create-batches")
# def create_registry_batches(filters: RegistryFilters):
#     filter_payload = filters.dict()
#     conn = get_connection()

#     try:
#         with conn:
#             with conn.cursor() as cur:
#                 ensure_registry_columns(cur)
#                 ensure_kp_request_schema(cur)

#                 kp_request = resolve_kp_request(cur, filters)

#                 if kp_request:
#                     item_ids = resolve_kp_request_item_ids(cur, kp_request["kp_request_id"])
#                     filters.kp_request_id = kp_request["kp_request_id"]
#                     filters.kp_request_code = kp_request["kp_request_code"]
#                     filter_payload = filters.dict()
#                 else:
#                     item_ids = resolve_registry_item_ids(cur, filters)

#                 if not item_ids:
#                     return {
#                         "status": "NO_SELECTED_ITEMS",
#                         "message": "Нет позиций, отмеченных для участия в отборе.",
#                         "items_count": 0,
#                         "supplier_results_count": 0,
#                         "batches_count": 0,
#                         "batch_ids": [],
#                         "kp_request_id": kp_request["kp_request_id"] if kp_request else None,
#                         "kp_request_code": kp_request["kp_request_code"] if kp_request else None,
#                     }

#                 created_batches, batch_ids, supplier_results_count = create_email_batches_from_results(
#                     cur,
#                     item_ids,
#                     filter_payload,
#                     kp_request_id=kp_request["kp_request_id"] if kp_request else None,
#                     kp_request_code=kp_request["kp_request_code"] if kp_request else None,
#                 )

#                 if supplier_results_count == 0:
#                     return {
#                         "status": "NO_SUPPLIERS",
#                         "message": "Сначала выполните подбор поставщиков. Сейчас результатов подбора нет.",
#                         "items_count": len(item_ids),
#                         "supplier_results_count": 0,
#                         "batches_count": 0,
#                         "batch_ids": [],
#                         "kp_request_id": kp_request["kp_request_id"] if kp_request else None,
#                         "kp_request_code": kp_request["kp_request_code"] if kp_request else None,
#                     }

#                 return {
#                     "status": "OK" if created_batches else "NO_BATCHES_CREATED",
#                     "message": f"Черновики писем сформированы. Черновиков создано: {created_batches}.",
#                     "items_count": len(item_ids),
#                     "supplier_results_count": supplier_results_count,
#                     "batches_count": created_batches,
#                     "batch_ids": batch_ids,
#                     "kp_request_id": kp_request["kp_request_id"] if kp_request else None,
#                     "kp_request_code": kp_request["kp_request_code"] if kp_request else None,
#                 }

#     except HTTPException:
#         raise
#     except Exception as error:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Ошибка формирования черновиков по реестру: {str(error)}",
#         )
#     finally:
#         conn.close()



# @router.get("/registry/kp-requests")
# def get_kp_requests(limit: int = 500):
#     """Реестр созданных запросов КП: КП00001, КП00002 и т.д."""
#     limit = max(1, min(limit, 2000))

#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_registry_columns(cur)
#             ensure_kp_request_schema(cur)
#             conn.commit()

#     return fetch_all(
#         """
#         SELECT
#             kr.kp_request_id,
#             kr.kp_request_code,
#             kr.status,
#             kr.created_at,
#             kr.updated_at,
#             COALESCE(items.items_count, 0) AS items_count,
#             COALESCE(results.supplier_results_count, 0) AS supplier_results_count,
#             COALESCE(batches.batches_count, 0) AS batches_count,
#             COALESCE(batches.sent_batches_count, 0) AS sent_batches_count,
#             COALESCE(batches.error_batches_count, 0) AS error_batches_count,
#             COALESCE(logs.sent_logs_count, 0) AS sent_logs_count,
#             batches.last_sent_at
#         FROM kp_requests kr
#         LEFT JOIN (
#             SELECT kp_request_id, COUNT(DISTINCT item_id) AS items_count
#             FROM kp_request_items
#             GROUP BY kp_request_id
#         ) items
#             ON items.kp_request_id = kr.kp_request_id
#         LEFT JOIN (
#             SELECT kp_request_id, COUNT(*) AS supplier_results_count
#             FROM supplier_search_results
#             WHERE kp_request_id IS NOT NULL
#             GROUP BY kp_request_id
#         ) results
#             ON results.kp_request_id = kr.kp_request_id
#         LEFT JOIN (
#             SELECT
#                 kp_request_id,
#                 COUNT(*) AS batches_count,
#                 COUNT(*) FILTER (WHERE status = 'SENT') AS sent_batches_count,
#                 COUNT(*) FILTER (WHERE status = 'SEND_ERROR') AS error_batches_count,
#                 MAX(updated_at) FILTER (WHERE status = 'SENT') AS last_sent_at
#             FROM procurement_email_batches
#             WHERE kp_request_id IS NOT NULL
#             GROUP BY kp_request_id
#         ) batches
#             ON batches.kp_request_id = kr.kp_request_id
#         LEFT JOIN (
#             SELECT b.kp_request_id, COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count
#             FROM procurement_email_batches b
#             LEFT JOIN procurement_email_logs l
#                 ON l.batch_id = b.batch_id
#             WHERE b.kp_request_id IS NOT NULL
#             GROUP BY b.kp_request_id
#         ) logs
#             ON logs.kp_request_id = kr.kp_request_id
#         ORDER BY kr.created_at DESC, kr.kp_request_id DESC
#         LIMIT %s
#         """,
#         (limit,),
#     )


# @router.get("/registry/kp-requests/{kp_request_id}")
# def get_kp_request_detail(kp_request_id: int):
#     """Детальная карточка запроса КП: позиции, найденные поставщики, черновики."""
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_registry_columns(cur)
#             ensure_kp_request_schema(cur)
#             conn.commit()

#     request = fetch_one(
#         """
#         SELECT *
#         FROM kp_requests
#         WHERE kp_request_id = %s
#         """,
#         (kp_request_id,),
#     )

#     if not request:
#         raise HTTPException(status_code=404, detail="КП-запрос не найден")

#     items = fetch_all(
#         """
#         SELECT
#             kri.kp_request_id,
#             a.application_id,
#             a.application_no,
#             a.application_date,
#             a.construction_object,
#             COALESCE(NULLIF(a.contract_no, ''), contract_base.contract_no, contract_link.contract_no) AS contract_no,
#             COALESCE(a.contract_date::text, contract_base.contract_date::text, contract_link.contract_date) AS contract_date,
#             COALESCE(NULLIF(contract_link.contract_appendix, ''), NULLIF(a.contract_appendix, '')) AS contract_appendix,
#             i.item_id,
#             i.material_id,
#             i.okpd2_code_from_application,
#             COALESCE(i.okpd2_code_from_application, mom.okpd2_code) AS okpd2_code,
#             COALESCE(i.user_group_id_from_application, mugm.id_possition) AS user_group_id,
#             i.material_name,
#             COALESCE(u.unit_name, i.unit) AS unit,
#             i.quantity,
#             i.characteristics_comment,
#             i.work_doc_code,
#             COALESCE(NULLIF(i.work_doc_subject, ''), contract_link.work_doc_subject) AS work_doc_subject,
#             i.supply_start_date,
#             i.supply_end_date,
#             i.processing_status,
#             CASE
#                 WHEN i.supply_start_date IS NOT NULL AND i.supply_end_date IS NOT NULL
#                     THEN i.supply_start_date::text || ' — ' || i.supply_end_date::text
#                 WHEN i.supply_start_date IS NOT NULL
#                     THEN i.supply_start_date::text
#                 WHEN i.supply_end_date IS NOT NULL
#                     THEN i.supply_end_date::text
#                 ELSE NULL
#             END AS supply_period
#         FROM kp_request_items kri
#         JOIN purchase_application_items i
#             ON i.item_id = kri.item_id
#         JOIN purchase_applications a
#             ON a.application_id = i.application_id
#         LEFT JOIN material_okpd2_map mom
#             ON trim(mom.material_id) = trim(i.material_id)
#         AND mom.is_active = true
#         LEFT JOIN material_user_group_map mugm
#             ON trim(mugm.material_id) = trim(i.material_id)
#         LEFT JOIN contracts contract_base
#             ON contract_base.contract_id = a.contract_id
#         LEFT JOIN LATERAL (
#             SELECT
#                 string_agg(DISTINCT c.contract_no, ', ' ORDER BY c.contract_no) AS contract_no,
#                 string_agg(DISTINCT c.contract_date::text, ', ' ORDER BY c.contract_date::text) FILTER (WHERE c.contract_date IS NOT NULL) AS contract_date,
#                 string_agg(DISTINCT l.contract_appendix, ', ' ORDER BY l.contract_appendix) AS contract_appendix,
#                 string_agg(DISTINCT l.work_doc_subject, ', ' ORDER BY l.work_doc_subject) AS work_doc_subject
#             FROM contract_work_doc_subjects l
#             JOIN contracts c
#                 ON c.contract_id = l.contract_id
#             WHERE (NULLIF(btrim(a.contract_id), '') IS NULL OR l.contract_id = a.contract_id)
#               AND lower(btrim(l.work_doc_code)) = lower(btrim(i.work_doc_code))
#               AND (
#                     NULLIF(btrim(i.work_doc_subject), '') IS NULL
#                     OR lower(btrim(l.work_doc_subject)) = lower(btrim(i.work_doc_subject))
#                   )
#         ) contract_link ON true
#         LEFT JOIN units u
#             ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
#             OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
#         WHERE kri.kp_request_id = %s
#         ORDER BY a.application_id, i.source_row_no NULLS LAST, i.item_id
#         """,
#         (kp_request_id,),
#     )

#     supplier_results = fetch_all(
#         """
#         SELECT
#             row_number() OVER (
#                 ORDER BY
#                     supplier_name,
#                     supplier_inn,
#                     search_method,
#                     item_id
#             ) AS result_no,
#             kp_request_id,
#             kp_request_code,
#             item_id,
#             supplier_id,
#             supplier_inn,
#             supplier_name,
#             search_method,
#             source_system,
#             material_id,
#             okpd2_code,
#             okved2_code,
#             user_group_id,
#             match_reason,
#             created_at
#         FROM supplier_search_results
#         WHERE kp_request_id = %s
#         ORDER BY search_method, supplier_name, supplier_inn, item_id
#         """,
#         (kp_request_id,),
#     )

#     batches = fetch_all(
#         """
#         SELECT
#             b.*,
#             s.email AS supplier_email,
#             COUNT(DISTINCT bi.item_id) AS items_count,
#             COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count,
#             MAX(l.sent_at) AS last_sent_at
#         FROM procurement_email_batches b
#         LEFT JOIN procurement_email_batch_items bi
#             ON bi.batch_id = b.batch_id
#         LEFT JOIN suppliers s
#             ON s.inn = b.supplier_inn
#         LEFT JOIN procurement_email_logs l
#             ON l.batch_id = b.batch_id
#         WHERE b.kp_request_id = %s
#         GROUP BY b.batch_id, s.email
#         ORDER BY b.search_method, b.supplier_name, b.supplier_inn
#         """,
#         (kp_request_id,),
#     )

#     return {
#         "request": request,
#         "items": items,
#         "supplier_results": supplier_results,
#         "batches": batches,
#     }


# @router.get("/{application_id}")
# def get_application(application_id: int):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_registry_columns(cur)
#             conn.commit()

#     application = fetch_one(
#         """
#         SELECT *
#         FROM purchase_applications
#         WHERE application_id = %s
#         """,
#         (application_id,),
#     )

#     if not application:
#         raise HTTPException(status_code=404, detail="Заявка не найдена")

#     items = fetch_all(
#         """
#         SELECT
#             i.*,
#             COALESCE(u.unit_name, i.unit) AS unit
#         FROM purchase_application_items i
#         LEFT JOIN units u
#             ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
#             OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
#         WHERE i.application_id = %s
#         ORDER BY i.source_row_no, i.item_id
#         """,
#         (application_id,),
#     )

#     return {
#         "application": application,
#         "items": items,
#     }


# @router.get("/{application_id}/items")
# def get_application_items(application_id: int):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_registry_columns(cur)
#             conn.commit()

#     return fetch_all(
#         """
#         SELECT
#             i.*,
#             COALESCE(u.unit_name, i.unit) AS unit
#         FROM purchase_application_items i
#         LEFT JOIN units u
#             ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
#             OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
#         WHERE i.application_id = %s
#         ORDER BY i.source_row_no, i.item_id
#         """,
#         (application_id,),
#     )


import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import get_connection, fetch_all, fetch_one
from app.services.material_okpd2 import ensure_material_okpd2_active_schema
from app.services.suppliers import ensure_supplier_id_schema
from app.services.units import ensure_unit_names_storage


router = APIRouter()


class RegistryFilters(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    application_no: Optional[str] = None
    construction_object: Optional[str] = None
    material: Optional[str] = None
    unit: Optional[str] = None
    work_doc_code: Optional[str] = None
    okpd2_code: Optional[str] = None
    user_group_id: Optional[str] = None
    supplier_search_method: Optional[str] = None
    processing_status: Optional[str] = None
    only_search_enabled: bool = False
    item_ids: list[int] = Field(default_factory=list)

    # ID конкретного запроса КП, например КП00001.
    # Используется на шаге формирования черновиков, чтобы брать именно тот набор позиций,
    # который был выбран при нажатии «Создать запрос КП».
    kp_request_id: Optional[int] = None
    kp_request_code: Optional[str] = None


class RegistryItemUpdate(BaseModel):
    supplier_search_method: Optional[str] = None
    search_enabled: Optional[bool] = None


def ensure_registry_columns(cur):
    ensure_material_okpd2_active_schema(cur)
    """Безопасно добавляет технические поля реестра, если база была создана до доработок."""
    cur.execute(
        """
        ALTER TABLE purchase_application_items
        ADD COLUMN IF NOT EXISTS add_to_search boolean DEFAULT false,
        ADD COLUMN IF NOT EXISTS supplier_search_method text DEFAULT 'AI_SPARK',
        ADD COLUMN IF NOT EXISTS processing_status text DEFAULT 'NEW',
        ADD COLUMN IF NOT EXISTS work_doc_subject text,
        ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now()
        """
    )

    cur.execute(
        """
        ALTER TABLE purchase_applications
        ADD COLUMN IF NOT EXISTS contract_id text,
        ADD COLUMN IF NOT EXISTS contract_no text,
        ADD COLUMN IF NOT EXISTS contract_date date,
        ADD COLUMN IF NOT EXISTS contract_appendix text,
        ADD COLUMN IF NOT EXISTS contract_subject text
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contracts (
            contract_id text PRIMARY KEY,
            contract_no text,
            contract_date date,
            contract_appendix text,
            created_at timestamptz DEFAULT now() NOT NULL,
            updated_at timestamptz DEFAULT now() NOT NULL
        )
        """
    )
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_no text")
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_date date")
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_appendix text")
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now() NOT NULL")
    cur.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now() NOT NULL")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_work_doc_subjects (
            contract_id text NOT NULL,
            contract_appendix text NOT NULL DEFAULT '-',
            work_doc_code text NOT NULL,
            work_doc_subject text NOT NULL,
            created_at timestamptz DEFAULT now() NOT NULL,
            updated_at timestamptz DEFAULT now() NOT NULL
        )
        """
    )
    cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS contract_appendix text")
    cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now() NOT NULL")
    cur.execute("ALTER TABLE contract_work_doc_subjects ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now() NOT NULL")
    cur.execute("UPDATE contract_work_doc_subjects SET contract_appendix = '-' WHERE NULLIF(btrim(contract_appendix), '') IS NULL")

    cur.execute(
        """
        ALTER TABLE purchase_application_items
        ALTER COLUMN add_to_search SET DEFAULT false
        """
    )

    cur.execute(
        """
        ALTER TABLE purchase_application_items
        DROP CONSTRAINT IF EXISTS purchase_application_items_supplier_search_method_check
        """
    )

    cur.execute(
        """
        UPDATE purchase_application_items
        SET
            add_to_search = COALESCE(add_to_search, false),
            supplier_search_method = CASE
                WHEN supplier_search_method IN ('AI', 'SPARK', 'AI_SPARK') THEN supplier_search_method
                ELSE 'AI_SPARK'
            END,
            processing_status = COALESCE(NULLIF(processing_status, ''), 'NEW')
        WHERE
            add_to_search IS NULL
            OR supplier_search_method IS NULL
            OR supplier_search_method = ''
            OR supplier_search_method NOT IN ('AI', 'SPARK', 'AI_SPARK')
            OR processing_status IS NULL
            OR processing_status = ''
        """
    )

    cur.execute(
        """
        ALTER TABLE purchase_application_items
        ADD CONSTRAINT purchase_application_items_supplier_search_method_check
        CHECK (
            supplier_search_method IS NULL
            OR supplier_search_method IN ('AI', 'SPARK', 'AI_SPARK')
        )
        """
    )


    ensure_supplier_id_schema(cur)
    ensure_unit_names_storage(cur)


def ensure_kp_request_schema(cur):
    """Создаёт таблицы и колонки для сущности запроса КП, например КП00001."""
    cur.execute("CREATE SEQUENCE IF NOT EXISTS kp_request_seq START 1")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS kp_requests (
            kp_request_id integer PRIMARY KEY DEFAULT nextval('kp_request_seq'),
            kp_request_code text UNIQUE NOT NULL,
            status text DEFAULT 'SUPPLIERS_SEARCHED',
            filter_payload jsonb,
            created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now()
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS kp_request_items (
            kp_request_id integer NOT NULL REFERENCES kp_requests(kp_request_id) ON DELETE CASCADE,
            item_id integer NOT NULL REFERENCES purchase_application_items(item_id) ON DELETE CASCADE,
            PRIMARY KEY (kp_request_id, item_id)
        )
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kp_request_items_item_id
        ON kp_request_items(item_id)
        """
    )

    cur.execute(
        """
        ALTER TABLE supplier_search_results
        ADD COLUMN IF NOT EXISTS kp_request_id integer,
        ADD COLUMN IF NOT EXISTS kp_request_code text
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_supplier_search_results_kp_request_id
        ON supplier_search_results(kp_request_id)
        """
    )

    cur.execute(
        """
        ALTER TABLE procurement_email_batches
        ADD COLUMN IF NOT EXISTS kp_request_id integer,
        ADD COLUMN IF NOT EXISTS kp_request_code text
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procurement_email_batches_kp_request_id
        ON procurement_email_batches(kp_request_id)
        """
    )


def create_kp_request(cur, item_ids: list[int], filter_payload: dict):
    cur.execute("SELECT nextval('kp_request_seq') AS n")
    number = cur.fetchone()["n"]
    kp_request_code = f"КП{number:05d}"

    cur.execute(
        """
        INSERT INTO kp_requests (
            kp_request_id,
            kp_request_code,
            status,
            filter_payload
        )
        VALUES (%s, %s, 'SUPPLIERS_SEARCHED', %s::jsonb)
        RETURNING kp_request_id, kp_request_code
        """,
        (
            number,
            kp_request_code,
            json.dumps(filter_payload, ensure_ascii=False, default=str),
        ),
    )
    request = cur.fetchone()

    cur.execute(
        """
        INSERT INTO kp_request_items (kp_request_id, item_id)
        SELECT %s, unnest(%s::int[])
        ON CONFLICT DO NOTHING
        """,
        (request["kp_request_id"], item_ids),
    )

    return request


def resolve_kp_request(cur, filters: RegistryFilters):
    if filters.kp_request_id:
        cur.execute(
            """
            SELECT kp_request_id, kp_request_code
            FROM kp_requests
            WHERE kp_request_id = %s
            """,
            (filters.kp_request_id,),
        )
    elif filters.kp_request_code:
        cur.execute(
            """
            SELECT kp_request_id, kp_request_code
            FROM kp_requests
            WHERE kp_request_code = %s
            """,
            (filters.kp_request_code,),
        )
    else:
        return None

    request = cur.fetchone()

    if not request:
        raise HTTPException(status_code=404, detail="КП-запрос не найден")

    return request


def resolve_kp_request_item_ids(cur, kp_request_id: int):
    cur.execute(
        """
        SELECT item_id
        FROM kp_request_items
        WHERE kp_request_id = %s
        ORDER BY item_id
        """,
        (kp_request_id,),
    )
    return [row["item_id"] for row in cur.fetchall()]




def supplier_method_wants_spark(method: str) -> bool:
    return (method or "AI_SPARK") in ("SPARK", "AI_SPARK")


def supplier_method_wants_ai(method: str) -> bool:
    return (method or "AI_SPARK") in ("AI", "AI_SPARK")


def collect_supplier_mapping_issues(cur, item_ids: list[int]):
    """Проверяет, достаточно ли связей для подбора поставщиков по выбранным позициям.

    Для каждой позиции должен существовать хотя бы один полный маршрут, разрешённый
    выбранным способом поиска:
    - SPARK: Материал → ОКПД2 → ОКВЭД2 → Поставщик;
    - AI: Материал → Группа материалов → Поставщик.

    Если ни один разрешённый маршрут не полон, КП-запрос не создаём и возвращаем
    пользователю список конкретных связей, которые нужно добавить в справочниках.
    """
    if not item_ids:
        return {"can_create_kp": True, "missing_links": [], "blocked_items_count": 0}

    cur.execute(
        """
        WITH selected_items AS (
            SELECT
                i.item_id,
                i.material_id,
                i.material_name,
                COALESCE(i.supplier_search_method, 'AI_SPARK') AS supplier_search_method,
                NULLIF(btrim(i.okpd2_code_from_application), '') AS okpd2_from_application,
                NULLIF(btrim(i.user_group_id_from_application), '') AS user_group_from_application
            FROM purchase_application_items i
            WHERE i.item_id = ANY(%s)
              AND i.add_to_search = true
        ),
        resolved AS (
            SELECT
                si.*,
                COALESCE(si.okpd2_from_application, mom.okpd2_code) AS resolved_okpd2_code,
                COALESCE(si.user_group_from_application, mugm.id_possition) AS resolved_user_group_id
            FROM selected_items si
            LEFT JOIN material_okpd2_map mom
                ON btrim(mom.material_id) = btrim(si.material_id)
               AND mom.is_active = true
            LEFT JOIN material_user_group_map mugm
                ON btrim(mugm.material_id) = btrim(si.material_id)
        ),
        spark_stats AS (
            SELECT
                r.item_id,
                EXISTS (
                    SELECT 1
                    FROM okpd2_okved2_map oom
                    WHERE btrim(oom.okpd2_code) = btrim(r.resolved_okpd2_code)
                ) AS has_okpd2_okved2,
                EXISTS (
                    SELECT 1
                    FROM okpd2_okved2_map oom
                    JOIN suppliers s
                      ON btrim(s.okved2_code) = btrim(oom.okved2_code)
                    WHERE btrim(oom.okpd2_code) = btrim(r.resolved_okpd2_code)
                      AND s.inn IS NOT NULL
                      AND btrim(s.inn) <> ''
                ) AS has_spark_supplier,
                (
                    SELECT string_agg(DISTINCT oom.okved2_code, ', ' ORDER BY oom.okved2_code)
                    FROM okpd2_okved2_map oom
                    WHERE btrim(oom.okpd2_code) = btrim(r.resolved_okpd2_code)
                ) AS okved2_codes
            FROM resolved r
        ),
        ai_stats AS (
            SELECT
                r.item_id,
                EXISTS (
                    SELECT 1
                    FROM user_group_supply_map ugsm
                    WHERE ugsm.user_group_id = r.resolved_user_group_id
                      AND NULLIF(btrim(ugsm.supplier_id::text), '') IS NOT NULL
                ) AS has_group_supplier_link,
                EXISTS (
                    SELECT 1
                    FROM user_group_supply_map ugsm
                    JOIN suppliers s
                      ON s.supplier_id::text = ugsm.supplier_id::text
                    WHERE ugsm.user_group_id = r.resolved_user_group_id
                      AND NULLIF(btrim(ugsm.supplier_id::text), '') IS NOT NULL
                ) AS has_ai_supplier
            FROM resolved r
        )
        SELECT
            r.item_id,
            r.material_id,
            r.material_name,
            r.supplier_search_method,
            r.resolved_okpd2_code,
            r.resolved_user_group_id,
            COALESCE(ss.has_okpd2_okved2, false) AS has_okpd2_okved2,
            COALESCE(ss.has_spark_supplier, false) AS has_spark_supplier,
            ss.okved2_codes,
            COALESCE(ai.has_group_supplier_link, false) AS has_group_supplier_link,
            COALESCE(ai.has_ai_supplier, false) AS has_ai_supplier
        FROM resolved r
        LEFT JOIN spark_stats ss ON ss.item_id = r.item_id
        LEFT JOIN ai_stats ai ON ai.item_id = r.item_id
        ORDER BY r.item_id
        """,
        (item_ids,),
    )

    rows = cur.fetchall()
    missing_links = []
    blocked_item_ids = set()

    def add_issue(row, route, link_type, action, mapping_page, details=None):
        missing_links.append({
            "item_id": row.get("item_id"),
            "material_id": row.get("material_id"),
            "material_name": row.get("material_name"),
            "supplier_search_method": row.get("supplier_search_method") or "AI_SPARK",
            "route": route,
            "missing_link_type": link_type,
            "need_to_add": action,
            "mapping_page": mapping_page,
            "details": details or "",
        })

    for row in rows:
        method = row.get("supplier_search_method") or "AI_SPARK"
        wants_spark = supplier_method_wants_spark(method)
        wants_ai = supplier_method_wants_ai(method)
        spark_ok = False
        ai_ok = False
        item_issue_count_before = len(missing_links)

        if wants_spark:
            if not row.get("resolved_okpd2_code"):
                add_issue(
                    row,
                    "SPARK",
                    "Материал → ОКПД2",
                    "Добавьте активную связь материала с кодом ОКПД2",
                    "Мэппинги → Материал → ОКПД2",
                )
            elif not row.get("has_okpd2_okved2"):
                add_issue(
                    row,
                    "SPARK",
                    "ОКПД2 → ОКВЭД2",
                    "Добавьте связь ОКПД2 с ОКВЭД2",
                    "Мэппинги → ОКПД2 → ОКВЭД2",
                    f"ОКПД2: {row.get('resolved_okpd2_code')}",
                )
            elif not row.get("has_spark_supplier"):
                add_issue(
                    row,
                    "SPARK",
                    "ОКВЭД2 → Поставщик",
                    "Добавьте поставщика с подходящим ОКВЭД2 в справочник поставщиков",
                    "Справочники → Поставщики",
                    f"ОКВЭД2: {row.get('okved2_codes') or 'не найден'}",
                )
            else:
                spark_ok = True

        if wants_ai:
            if not row.get("resolved_user_group_id"):
                add_issue(
                    row,
                    "AI",
                    "Материал → Группа материалов",
                    "Добавьте связь материала с группой материалов",
                    "Мэппинги → Материал → Группа",
                )
            elif not row.get("has_group_supplier_link") or not row.get("has_ai_supplier"):
                add_issue(
                    row,
                    "AI",
                    "Группа материалов → Поставщик",
                    "Добавьте связь группы материалов с поставщиком",
                    "Мэппинги → Группа → Поставщик",
                    f"Группа: {row.get('resolved_user_group_id')}",
                )
            else:
                ai_ok = True

        has_allowed_route = (wants_spark and spark_ok) or (wants_ai and ai_ok)
        if not has_allowed_route:
            blocked_item_ids.add(row.get("item_id"))
        else:
            # Если маршрут хотя бы один рабочий, не блокируем КП. Удаляем предупреждения
            # по запасному маршруту, чтобы пользователь видел только действительно критичные связи.
            del missing_links[item_issue_count_before:]

    return {
        "can_create_kp": len(blocked_item_ids) == 0,
        "missing_links": missing_links,
        "blocked_items_count": len(blocked_item_ids),
    }

def build_registry_where(filters: RegistryFilters):
    where = []
    params = []

    if filters.only_search_enabled:
        where.append("i.add_to_search = true")

    if filters.date_from:
        where.append("(i.supply_end_date IS NULL OR i.supply_end_date >= %s)")
        params.append(filters.date_from)

    if filters.date_to:
        where.append("(i.supply_start_date IS NULL OR i.supply_start_date <= %s)")
        params.append(filters.date_to)

    if filters.application_no:
        where.append(
            """
            (
                lower(COALESCE(a.application_no, '')) LIKE lower(%s)
                OR a.application_id::text LIKE %s
            )
            """
        )
        params.extend([f"%{filters.application_no}%", f"%{filters.application_no}%"])

    if filters.construction_object:
        where.append("lower(COALESCE(a.construction_object, '')) LIKE lower(%s)")
        params.append(f"%{filters.construction_object}%")

    if filters.material:
        where.append(
            """
            (
                lower(COALESCE(i.material_name, '')) LIKE lower(%s)
                OR lower(COALESCE(i.material_id, '')) LIKE lower(%s)
            )
            """
        )
        params.extend([f"%{filters.material}%", f"%{filters.material}%"])

    if filters.unit:
        where.append(
            """
            (
                lower(COALESCE(i.unit, '')) LIKE lower(%s)
                OR lower(COALESCE(u.unit_name, '')) LIKE lower(%s)
                OR lower(COALESCE(u.unit_code, '')) LIKE lower(%s)
            )
            """
        )
        params.extend([f"%{filters.unit}%", f"%{filters.unit}%", f"%{filters.unit}%"])

    if filters.work_doc_code:
        where.append("lower(COALESCE(i.work_doc_code, '')) LIKE lower(%s)")
        params.append(f"%{filters.work_doc_code}%")

    if filters.okpd2_code:
        where.append("btrim(COALESCE(mom.okpd2_code, '')) = btrim(%s)")
        params.append(filters.okpd2_code)

    if filters.user_group_id:
        where.append("COALESCE(i.user_group_id_from_application, mugm.id_possition) = %s")
        params.append(filters.user_group_id)

    if filters.supplier_search_method:
        where.append("COALESCE(i.supplier_search_method, 'AI_SPARK') = %s")
        params.append(filters.supplier_search_method)

    if filters.processing_status:
        where.append("i.processing_status = %s")
        params.append(filters.processing_status)

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    return where_sql, params


def resolve_registry_item_ids(cur, filters: RegistryFilters):
    if filters.item_ids:
        item_ids = list(dict.fromkeys(int(item_id) for item_id in filters.item_ids if item_id))
    else:
        where_sql, params = build_registry_where(filters)
        cur.execute(
            f"""
            SELECT i.item_id
            FROM purchase_application_items i
            JOIN purchase_applications a
                ON a.application_id = i.application_id
            LEFT JOIN material_okpd2_map mom
                ON trim(mom.material_id) = trim(i.material_id)
            AND mom.is_active = true
            LEFT JOIN material_user_group_map mugm
                ON trim(mugm.material_id) = trim(i.material_id)
            LEFT JOIN units u
                ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
                OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
            {where_sql}
            """,
            tuple(params),
        )
        item_ids = [row["item_id"] for row in cur.fetchall()]

    if not item_ids:
        return []

    cur.execute(
        """
        SELECT item_id
        FROM purchase_application_items
        WHERE item_id = ANY(%s)
          AND add_to_search = true
        ORDER BY item_id
        """,
        (item_ids,),
    )
    return [row["item_id"] for row in cur.fetchall()]


def run_supplier_search(cur, item_ids: list[int], kp_request_id: int, kp_request_code: str):
    cur.execute(
        """
        DELETE FROM supplier_search_results
        WHERE kp_request_id = %s
        """,
        (kp_request_id,),
    )

    # SPARK: Material → OKPD2 → OKVED2 → suppliers
    cur.execute(
        """
        INSERT INTO supplier_search_results (
            kp_request_id,
            kp_request_code,
            item_id,
            supplier_id,
            search_method,
            source_system,
            material_id,
            okpd2_code,
            okved2_code,
            user_group_id,
            supplier_inn,
            supplier_name,
            match_reason
        )
        SELECT DISTINCT
            %s AS kp_request_id,
            %s AS kp_request_code,
            i.item_id,
            sr.supplier_id,
            'SPARK' AS search_method,
            'SPARK' AS source_system,
            trim(i.material_id) AS material_id,
            trim(COALESCE(i.okpd2_code_from_application, mom.okpd2_code)) AS okpd2_code,
            trim(oom.okved2_code) AS okved2_code,
            NULL::text AS user_group_id,
            trim(sr.inn) AS supplier_inn,
            sr.name AS supplier_name,
            'Реестр: Material → OKPD2 → OKVED2 → suppliers / SPARK'
        FROM purchase_application_items i
        LEFT JOIN material_okpd2_map mom
            ON trim(mom.material_id) = trim(i.material_id)
        AND mom.is_active = true
        JOIN okpd2_okved2_map oom
            ON trim(oom.okpd2_code) = trim(COALESCE(i.okpd2_code_from_application, mom.okpd2_code))
        JOIN suppliers sr
            ON trim(sr.okved2_code) = trim(oom.okved2_code)
        WHERE i.item_id = ANY(%s)
          AND i.add_to_search = true
          AND COALESCE(i.supplier_search_method, 'AI_SPARK') IN ('SPARK', 'AI_SPARK')
          AND i.material_id IS NOT NULL
          AND trim(i.material_id) <> ''
          AND COALESCE(i.okpd2_code_from_application, mom.okpd2_code) IS NOT NULL
          AND trim(COALESCE(i.okpd2_code_from_application, mom.okpd2_code)) <> ''
          AND sr.inn IS NOT NULL
          AND trim(sr.inn) <> ''
        """,
        (kp_request_id, kp_request_code, item_ids),
    )

    # AI: Material → Group → suppliers
    cur.execute(
        """
        INSERT INTO supplier_search_results (
            kp_request_id,
            kp_request_code,
            item_id,
            supplier_id,
            search_method,
            source_system,
            material_id,
            okpd2_code,
            okved2_code,
            user_group_id,
            supplier_inn,
            supplier_name,
            match_reason
        )
        SELECT DISTINCT
            %s AS kp_request_id,
            %s AS kp_request_code,
            i.item_id,
            ugsm.supplier_id::text AS supplier_id,
            'AI' AS search_method,
            'AI' AS source_system,
            i.material_id,
            NULL::text AS okpd2_code,
            NULL::text AS okved2_code,
            COALESCE(i.user_group_id_from_application, mugm.id_possition) AS user_group_id,
            s.inn AS supplier_inn,
            COALESCE(NULLIF(s.name, ''), NULLIF(ugsm.supplier_id::text, ''), 'Не найдено') AS supplier_name,
            'Реестр: Material → Group → user_group_supply_map / suppliers'
        FROM purchase_application_items i
        LEFT JOIN material_user_group_map mugm
            ON trim(mugm.material_id) = trim(i.material_id)
        JOIN user_group_supply_map ugsm
            ON ugsm.user_group_id = COALESCE(i.user_group_id_from_application, mugm.id_possition)
        JOIN suppliers s
            ON s.supplier_id::text = ugsm.supplier_id::text
        WHERE i.item_id = ANY(%s)
          AND i.add_to_search = true
          AND COALESCE(i.supplier_search_method, 'AI_SPARK') IN ('AI', 'AI_SPARK')
          AND COALESCE(i.user_group_id_from_application, mugm.id_possition) IS NOT NULL
          AND NULLIF(btrim(ugsm.supplier_id::text), '') IS NOT NULL
        """,
        (kp_request_id, kp_request_code, item_ids),
    )

    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM supplier_search_results
        WHERE kp_request_id = %s
          AND item_id = ANY(%s)
        """,
        (kp_request_id, item_ids),
    )
    supplier_results_count = cur.fetchone()["cnt"]

    if supplier_results_count == 0:
        cur.execute(
            """
            UPDATE purchase_application_items
            SET processing_status = 'NO_SUPPLIERS',
                updated_at = now()
            WHERE item_id = ANY(%s)
            """,
            (item_ids,),
        )
        cur.execute(
            """
            UPDATE kp_requests
            SET status = 'NO_SUPPLIERS',
                updated_at = now()
            WHERE kp_request_id = %s
            """,
            (kp_request_id,),
        )
    else:
        cur.execute(
            """
            UPDATE purchase_application_items i
            SET processing_status = 'SUPPLIERS_FOUND',
                updated_at = now()
            WHERE i.item_id = ANY(%s)
              AND EXISTS (
                  SELECT 1
                  FROM supplier_search_results r
                  WHERE r.kp_request_id = %s
                    AND r.item_id = i.item_id
              )
            """,
            (item_ids, kp_request_id),
        )

        cur.execute(
            """
            UPDATE purchase_application_items i
            SET processing_status = 'NO_SUPPLIERS',
                updated_at = now()
            WHERE i.item_id = ANY(%s)
              AND NOT EXISTS (
                  SELECT 1
                  FROM supplier_search_results r
                  WHERE r.kp_request_id = %s
                    AND r.item_id = i.item_id
              )
            """,
            (item_ids, kp_request_id),
        )

    return supplier_results_count


def create_email_batches_from_results(
    cur,
    item_ids: list[int],
    filter_payload: dict,
    kp_request_id: Optional[int] = None,
    kp_request_code: Optional[str] = None,
):
    if kp_request_id:
        cur.execute(
            """
            DELETE FROM procurement_email_batches
            WHERE kp_request_id = %s
            """,
            (kp_request_id,),
        )

    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM supplier_search_results r
        WHERE r.item_id = ANY(%s)
          AND (%s IS NULL OR r.kp_request_id = %s)
        """,
        (item_ids, kp_request_id, kp_request_id),
    )
    supplier_results_count = cur.fetchone()["cnt"]

    if supplier_results_count == 0:
        return 0, [], 0

    cur.execute(
        """
        SELECT
            r.supplier_id,
            r.supplier_inn,
            r.supplier_name,
            r.search_method,
            r.okpd2_code,
            r.okved2_code,
            r.user_group_id,
            MIN(i.supply_start_date) AS supply_start_date,
            MAX(i.supply_end_date) AS supply_end_date,
            COUNT(DISTINCT r.item_id) AS items_count
        FROM supplier_search_results r
        JOIN purchase_application_items i
            ON i.item_id = r.item_id
        WHERE r.item_id = ANY(%s)
          AND (%s IS NULL OR r.kp_request_id = %s)
        GROUP BY
            r.supplier_id,
            r.supplier_inn,
            r.supplier_name,
            r.search_method,
            r.okpd2_code,
            r.okved2_code,
            r.user_group_id
        HAVING COUNT(DISTINCT r.item_id) > 0
        """,
        (item_ids, kp_request_id, kp_request_id),
    )

    groups = cur.fetchall()
    created_batches = 0
    batch_ids = []

    for group in groups:
        if not group["supplier_id"] and not group["supplier_inn"] and not group["supplier_name"]:
            continue

        cur.execute(
            """
            INSERT INTO procurement_email_batches (
                kp_request_id,
                kp_request_code,
                application_id,
                supplier_id,
                supplier_inn,
                supplier_name,
                search_method,
                okpd2_code,
                okved2_code,
                user_group_id,
                supply_start_date,
                supply_end_date,
                status,
                source_mode,
                filter_payload
            )
            VALUES (
                %s,
                %s,
                NULL,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'DRAFT',
                'REGISTRY',
                %s::jsonb
            )
            RETURNING batch_id
            """,
            (
                kp_request_id,
                kp_request_code,
                group["supplier_id"],
                group["supplier_inn"],
                group["supplier_name"],
                group["search_method"],
                group["okpd2_code"],
                group["okved2_code"],
                group["user_group_id"],
                group["supply_start_date"],
                group["supply_end_date"],
                json.dumps(filter_payload, ensure_ascii=False, default=str),
            ),
        )

        batch_id = cur.fetchone()["batch_id"]

        cur.execute(
            """
            INSERT INTO procurement_email_batch_items (batch_id, item_id)
            SELECT DISTINCT
                %s,
                r.item_id
            FROM supplier_search_results r
            WHERE r.item_id = ANY(%s)
              AND (%s IS NULL OR r.kp_request_id = %s)
              AND COALESCE(r.supplier_id::text, '') = COALESCE(%s::text, '')
              AND COALESCE(r.supplier_inn, '') = COALESCE(%s, '')
              AND COALESCE(r.supplier_name, '') = COALESCE(%s, '')
              AND r.search_method = %s
              AND COALESCE(r.okpd2_code, '') = COALESCE(%s, '')
              AND COALESCE(r.okved2_code, '') = COALESCE(%s, '')
              AND COALESCE(r.user_group_id, '') = COALESCE(%s, '')
            """,
            (
                batch_id,
                item_ids,
                kp_request_id,
                kp_request_id,
                group["supplier_id"],
                group["supplier_inn"],
                group["supplier_name"],
                group["search_method"],
                group["okpd2_code"],
                group["okved2_code"],
                group["user_group_id"],
            ),
        )

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM procurement_email_batch_items
            WHERE batch_id = %s
            """,
            (batch_id,),
        )

        batch_items_count = cur.fetchone()["cnt"]

        if batch_items_count == 0:
            cur.execute(
                """
                DELETE FROM procurement_email_batches
                WHERE batch_id = %s
                """,
                (batch_id,),
            )
        else:
            created_batches += 1
            batch_ids.append(batch_id)

    if created_batches:
        cur.execute(
            """
            UPDATE purchase_application_items
            SET processing_status = 'EMAIL_PREPARED',
                updated_at = now()
            WHERE item_id IN (
                SELECT item_id
                FROM procurement_email_batch_items
                WHERE batch_id = ANY(%s)
            )
            """,
            (batch_ids,),
        )

        if kp_request_id:
            cur.execute(
                """
                UPDATE kp_requests
                SET status = 'EMAIL_PREPARED',
                    updated_at = now()
                WHERE kp_request_id = %s
                """,
                (kp_request_id,),
            )

    return created_batches, batch_ids, supplier_results_count


@router.get("/")
def get_applications():
    """Возвращает реестр заявок и не теряет legacy-заявки после миграций.

    В старых БД часть заявок могла быть создана до появления новых полей договора
    или даже без полноценной строки в purchase_applications. Поэтому перед чтением
    синхронизируем схему, а список строим от фактических позиций тоже.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_registry_columns(cur)
            ensure_kp_request_schema(cur)
            conn.commit()

    return fetch_all(
        """
        WITH item_stats AS (
            SELECT
                application_id,
                COUNT(*) AS items_count
            FROM purchase_application_items
            GROUP BY application_id
        ),
        application_rows AS (
            SELECT
                a.application_id,
                COALESCE(NULLIF(a.application_no, ''), 'Заявка №' || a.application_id::text) AS application_no,
                a.application_date,
                a.construction_object,
                a.source_file_name,
                COALESCE(a.created_at, a.application_date::timestamptz) AS created_at,
                COALESCE(s.items_count, 0) AS items_count
            FROM purchase_applications a
            LEFT JOIN item_stats s
                ON s.application_id = a.application_id

            UNION ALL

            SELECT
                s.application_id,
                'Заявка №' || s.application_id::text AS application_no,
                NULL::date AS application_date,
                NULL::text AS construction_object,
                NULL::text AS source_file_name,
                NULL::timestamptz AS created_at,
                s.items_count
            FROM item_stats s
            LEFT JOIN purchase_applications a
                ON a.application_id = s.application_id
            WHERE a.application_id IS NULL
        )
        SELECT *
        FROM application_rows
        ORDER BY created_at DESC NULLS LAST, application_id DESC
        """
    )

def remove_uploaded_source_file(source_file_path: Optional[str]):
    """Удаляет исходный Excel-файл заявки только из локальной папки uploads."""
    if not source_file_path or source_file_path == "manual_input":
        return False

    uploads_dir = os.path.abspath("uploads")
    file_path = os.path.abspath(source_file_path)

    try:
        if os.path.commonpath([uploads_dir, file_path]) != uploads_dir:
            return False

        if os.path.isfile(file_path):
            os.remove(file_path)
            return True
    except Exception:
        return False

    return False

@router.delete("/{application_id}")
def delete_application(application_id: int):
    """Удаляет заявку и все связанные с ней позиции/материалы из рабочих реестров."""
    conn = get_connection()
    source_file_path = None

    try:
        with conn:
            with conn.cursor() as cur:
                ensure_registry_columns(cur)
                ensure_kp_request_schema(cur)

                cur.execute(
                    """
                    SELECT application_id, application_no, source_file_path
                    FROM purchase_applications
                    WHERE application_id = %s
                    """,
                    (application_id,),
                )
                application = cur.fetchone()

                if not application:
                    raise HTTPException(status_code=404, detail="Заявка не найдена")

                source_file_path = application.get("source_file_path")

                cur.execute(
                    """
                    SELECT item_id
                    FROM purchase_application_items
                    WHERE application_id = %s
                    """,
                    (application_id,),
                )
                item_ids = [row["item_id"] for row in cur.fetchall()]

                touched_batch_ids = []
                application_batch_ids = []
                touched_kp_request_ids = []
                deleted_batch_item_links = 0
                deleted_supplier_results = 0
                deleted_kp_item_links = 0
                deleted_items = 0
                deleted_batches = 0
                deleted_kp_requests = 0

                if item_ids:
                    cur.execute(
                        """
                        SELECT DISTINCT batch_id
                        FROM procurement_email_batch_items
                        WHERE item_id = ANY(%s)
                        """,
                        (item_ids,),
                    )
                    touched_batch_ids = [row["batch_id"] for row in cur.fetchall()]

                    cur.execute(
                        """
                        SELECT DISTINCT kp_request_id
                        FROM kp_request_items
                        WHERE item_id = ANY(%s)
                        """,
                        (item_ids,),
                    )
                    touched_kp_request_ids = [
                        row["kp_request_id"]
                        for row in cur.fetchall()
                        if row.get("kp_request_id")
                    ]

                cur.execute(
                    """
                    SELECT batch_id
                    FROM procurement_email_batches
                    WHERE application_id = %s
                    """,
                    (application_id,),
                )
                application_batch_ids = [row["batch_id"] for row in cur.fetchall()]

                all_known_batch_ids = list(dict.fromkeys(touched_batch_ids + application_batch_ids))

                if application_batch_ids:
                    cur.execute(
                        """
                        DELETE FROM procurement_email_batch_items
                        WHERE batch_id = ANY(%s)
                        """,
                        (application_batch_ids,),
                    )
                    deleted_batch_item_links += cur.rowcount or 0

                if item_ids:
                    cur.execute(
                        """
                        DELETE FROM procurement_email_batch_items
                        WHERE item_id = ANY(%s)
                        """,
                        (item_ids,),
                    )
                    deleted_batch_item_links += cur.rowcount or 0

                    cur.execute(
                        """
                        DELETE FROM supplier_search_results
                        WHERE item_id = ANY(%s)
                        """,
                        (item_ids,),
                    )
                    deleted_supplier_results = cur.rowcount or 0

                    cur.execute(
                        """
                        DELETE FROM kp_request_items
                        WHERE item_id = ANY(%s)
                        """,
                        (item_ids,),
                    )
                    deleted_kp_item_links = cur.rowcount or 0

                    cur.execute(
                        """
                        DELETE FROM purchase_application_items
                        WHERE application_id = %s
                        """,
                        (application_id,),
                    )
                    deleted_items = cur.rowcount or 0

                if all_known_batch_ids:
                    cur.execute(
                        """
                        DELETE FROM procurement_email_batches b
                        WHERE b.application_id = %s
                           OR (
                                b.batch_id = ANY(%s)
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM procurement_email_batch_items bi
                                    WHERE bi.batch_id = b.batch_id
                                )
                           )
                        """,
                        (application_id, all_known_batch_ids),
                    )
                    deleted_batches = cur.rowcount or 0
                else:
                    cur.execute(
                        """
                        DELETE FROM procurement_email_batches
                        WHERE application_id = %s
                        """,
                        (application_id,),
                    )
                    deleted_batches = cur.rowcount or 0

                if touched_kp_request_ids:
                    cur.execute(
                        """
                        DELETE FROM kp_requests kr
                        WHERE kr.kp_request_id = ANY(%s)
                          AND NOT EXISTS (
                              SELECT 1
                              FROM kp_request_items kri
                              WHERE kri.kp_request_id = kr.kp_request_id
                          )
                        """,
                        (touched_kp_request_ids,),
                    )
                    deleted_kp_requests = cur.rowcount or 0

                    cur.execute(
                        """
                        UPDATE kp_requests kr
                        SET status = CASE
                                WHEN COALESCE(stats.total_batches, 0) = 0 THEN kr.status
                                WHEN stats.sent_batches = stats.total_batches THEN 'EMAIL_SENT'
                                WHEN stats.sent_batches > 0 THEN 'PARTIALLY_SENT'
                                WHEN stats.error_batches > 0 THEN 'SEND_ERROR'
                                ELSE 'EMAIL_PREPARED'
                            END,
                            updated_at = now()
                        FROM (
                            SELECT
                                kp_request_id,
                                COUNT(*) AS total_batches,
                                COUNT(*) FILTER (WHERE status = 'SENT') AS sent_batches,
                                COUNT(*) FILTER (WHERE status = 'SEND_ERROR') AS error_batches
                            FROM procurement_email_batches
                            WHERE kp_request_id = ANY(%s)
                            GROUP BY kp_request_id
                        ) stats
                        WHERE kr.kp_request_id = stats.kp_request_id
                        """,
                        (touched_kp_request_ids,),
                    )

                cur.execute(
                    """
                    DELETE FROM purchase_applications
                    WHERE application_id = %s
                    """,
                    (application_id,),
                )

                return_payload = {
                    "status": "OK",
                    "application_id": application_id,
                    "application_no": application.get("application_no"),
                    "deleted_items_count": deleted_items,
                    "deleted_supplier_results_count": deleted_supplier_results,
                    "deleted_kp_item_links_count": deleted_kp_item_links,
                    "deleted_batch_item_links_count": deleted_batch_item_links,
                    "deleted_batches_count": deleted_batches,
                    "deleted_empty_kp_requests_count": deleted_kp_requests,
                }

        return_payload["source_file_deleted"] = remove_uploaded_source_file(source_file_path)
        return return_payload

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка удаления заявки: {str(error)}",
        )
    finally:
        conn.close()



@router.get("/registry")
def get_registry(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    application_no: Optional[str] = None,
    construction_object: Optional[str] = None,
    material: Optional[str] = None,
    unit: Optional[str] = None,
    work_doc_code: Optional[str] = None,
    okpd2_code: Optional[str] = None,
    user_group_id: Optional[str] = None,
    supplier_search_method: Optional[str] = None,
    processing_status: Optional[str] = None,
    only_search_enabled: bool = False,
):
    filters = RegistryFilters(
        date_from=date_from,
        date_to=date_to,
        application_no=application_no,
        construction_object=construction_object,
        material=material,
        unit=unit,
        work_doc_code=work_doc_code,
        okpd2_code=okpd2_code,
        user_group_id=user_group_id,
        supplier_search_method=supplier_search_method,
        processing_status=processing_status,
        only_search_enabled=only_search_enabled,
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_registry_columns(cur)
            ensure_kp_request_schema(cur)
            conn.commit()

    where_sql, params = build_registry_where(filters)

    return fetch_all(
        f"""
        SELECT
            a.application_id,
            a.application_no,
            a.application_date,
            a.construction_object,
            COALESCE(NULLIF(a.contract_no, ''), contract_base.contract_no, contract_link.contract_no) AS contract_no,
            COALESCE(a.contract_date::text, contract_base.contract_date::text, contract_link.contract_date) AS contract_date,
            COALESCE(NULLIF(contract_link.contract_appendix, ''), NULLIF(a.contract_appendix, '')) AS contract_appendix,

            i.item_id,
            i.material_id,

            COALESCE(i.okpd2_code_from_application, mom.okpd2_code) AS okpd2_code,
            COALESCE(i.user_group_id_from_application, mugm.id_possition) AS user_group_id,

            i.material_name,
            COALESCE(u.unit_name, i.unit) AS unit,
            i.quantity,
            i.characteristics_comment,
            i.work_doc_code,
            COALESCE(NULLIF(i.work_doc_subject, ''), contract_link.work_doc_subject) AS work_doc_subject,
            i.supply_start_date,
            i.supply_end_date,

            COALESCE(i.supplier_search_method, 'AI_SPARK') AS supplier_search_method,
            COALESCE(i.add_to_search, false) AS search_enabled,
            COALESCE(i.processing_status, 'NEW') AS processing_status,

            CASE
                WHEN i.supply_start_date IS NOT NULL AND i.supply_end_date IS NOT NULL
                    THEN i.supply_start_date::text || ' — ' || i.supply_end_date::text
                WHEN i.supply_start_date IS NOT NULL
                    THEN i.supply_start_date::text
                WHEN i.supply_end_date IS NOT NULL
                    THEN i.supply_end_date::text
                ELSE NULL
            END AS supply_period
        FROM purchase_application_items i
        JOIN purchase_applications a
            ON a.application_id = i.application_id
        LEFT JOIN material_okpd2_map mom
            ON trim(mom.material_id) = trim(i.material_id)
        AND mom.is_active = true
        LEFT JOIN material_user_group_map mugm
            ON trim(mugm.material_id) = trim(i.material_id)
        LEFT JOIN contracts contract_base
            ON contract_base.contract_id = a.contract_id
        LEFT JOIN LATERAL (
            SELECT
                string_agg(DISTINCT c.contract_no, ', ' ORDER BY c.contract_no) AS contract_no,
                string_agg(DISTINCT c.contract_date::text, ', ' ORDER BY c.contract_date::text) FILTER (WHERE c.contract_date IS NOT NULL) AS contract_date,
                string_agg(DISTINCT l.contract_appendix, ', ' ORDER BY l.contract_appendix) AS contract_appendix,
                string_agg(DISTINCT l.work_doc_subject, ', ' ORDER BY l.work_doc_subject) AS work_doc_subject
            FROM contract_work_doc_subjects l
            JOIN contracts c
                ON c.contract_id = l.contract_id
            WHERE (NULLIF(btrim(a.contract_id), '') IS NULL OR l.contract_id = a.contract_id)
              AND lower(btrim(l.work_doc_code)) = lower(btrim(i.work_doc_code))
              AND (
                    NULLIF(btrim(i.work_doc_subject), '') IS NULL
                    OR lower(btrim(l.work_doc_subject)) = lower(btrim(i.work_doc_subject))
                  )
        ) contract_link ON true
        LEFT JOIN units u
            ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
            OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
        {where_sql}
        ORDER BY
            COALESCE(i.supply_start_date, a.application_date) NULLS LAST,
            a.application_id DESC,
            i.source_row_no NULLS LAST,
            i.item_id
        """,
        tuple(params),
    )


@router.patch("/registry/items/{item_id}")
def update_registry_item(item_id: int, payload: RegistryItemUpdate):
    allowed_methods = {"AI", "SPARK", "AI_SPARK"}

    if payload.supplier_search_method and payload.supplier_search_method not in allowed_methods:
        raise HTTPException(
            status_code=400,
            detail="Способ поиска должен быть AI, SPARK или AI_SPARK",
        )

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                ensure_registry_columns(cur)

                cur.execute(
                    """
                    UPDATE purchase_application_items
                    SET
                        supplier_search_method = COALESCE(%s, supplier_search_method),
                        add_to_search = COALESCE(%s, add_to_search),
                        updated_at = now()
                    WHERE item_id = %s
                    RETURNING
                        item_id,
                        supplier_search_method,
                        add_to_search AS search_enabled,
                        processing_status
                    """,
                    (
                        payload.supplier_search_method,
                        payload.search_enabled,
                        item_id,
                    ),
                )

                updated = cur.fetchone()

                if not updated:
                    raise HTTPException(status_code=404, detail="Позиция не найдена")

                return {"status": "OK", "item": updated}

    finally:
        conn.close()


@router.post("/registry/search-suppliers")
def search_registry_suppliers(filters: RegistryFilters):
    filter_payload = filters.dict()
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                ensure_registry_columns(cur)
                ensure_kp_request_schema(cur)
                item_ids = resolve_registry_item_ids(cur, filters)

                if not item_ids:
                    return {
                        "status": "NO_SELECTED_ITEMS",
                        "message": "Нет позиций, отмеченных для участия в отборе.",
                        "items_count": 0,
                        "supplier_results_count": 0,
                        "kp_request_id": None,
                        "kp_request_code": None,
                    }

                readiness = collect_supplier_mapping_issues(cur, item_ids)

                if not readiness["can_create_kp"]:
                    return {
                        "status": "MAPPINGS_REQUIRED",
                        "message": (
                            "По выбранным позициям нельзя создать запрос КП: не хватает связей в справочниках. "
                            "Проверьте мэппинги и добавьте связи из списка ниже."
                        ),
                        "items_count": len(item_ids),
                        "blocked_items_count": readiness["blocked_items_count"],
                        "supplier_results_count": 0,
                        "filter_payload": filter_payload,
                        "kp_request_id": None,
                        "kp_request_code": None,
                        "missing_links": readiness["missing_links"],
                    }

                kp_request = create_kp_request(cur, item_ids, filter_payload)

                supplier_results_count = run_supplier_search(
                    cur,
                    item_ids,
                    kp_request["kp_request_id"],
                    kp_request["kp_request_code"],
                )

                return {
                    "status": "OK" if supplier_results_count else "NO_SUPPLIERS",
                    "message": "Подбор поставщиков завершён." if supplier_results_count else "По выбранным позициям поставщики не найдены.",
                    "items_count": len(item_ids),
                    "blocked_items_count": 0,
                    "supplier_results_count": supplier_results_count,
                    "filter_payload": filter_payload,
                    "kp_request_id": kp_request["kp_request_id"],
                    "kp_request_code": kp_request["kp_request_code"],
                    "missing_links": [],
                }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка подбора поставщиков по реестру: {str(error)}",
        )
    finally:
        conn.close()


@router.post("/registry/create-batches")
def create_registry_batches(filters: RegistryFilters):
    filter_payload = filters.dict()
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                ensure_registry_columns(cur)
                ensure_kp_request_schema(cur)

                kp_request = resolve_kp_request(cur, filters)

                if kp_request:
                    item_ids = resolve_kp_request_item_ids(cur, kp_request["kp_request_id"])
                    filters.kp_request_id = kp_request["kp_request_id"]
                    filters.kp_request_code = kp_request["kp_request_code"]
                    filter_payload = filters.dict()
                else:
                    item_ids = resolve_registry_item_ids(cur, filters)

                if not item_ids:
                    return {
                        "status": "NO_SELECTED_ITEMS",
                        "message": "Нет позиций, отмеченных для участия в отборе.",
                        "items_count": 0,
                        "supplier_results_count": 0,
                        "batches_count": 0,
                        "batch_ids": [],
                        "kp_request_id": kp_request["kp_request_id"] if kp_request else None,
                        "kp_request_code": kp_request["kp_request_code"] if kp_request else None,
                    }

                created_batches, batch_ids, supplier_results_count = create_email_batches_from_results(
                    cur,
                    item_ids,
                    filter_payload,
                    kp_request_id=kp_request["kp_request_id"] if kp_request else None,
                    kp_request_code=kp_request["kp_request_code"] if kp_request else None,
                )

                if supplier_results_count == 0:
                    return {
                        "status": "NO_SUPPLIERS",
                        "message": "Сначала выполните подбор поставщиков. Сейчас результатов подбора нет.",
                        "items_count": len(item_ids),
                        "supplier_results_count": 0,
                        "batches_count": 0,
                        "batch_ids": [],
                        "kp_request_id": kp_request["kp_request_id"] if kp_request else None,
                        "kp_request_code": kp_request["kp_request_code"] if kp_request else None,
                    }

                return {
                    "status": "OK" if created_batches else "NO_BATCHES_CREATED",
                    "message": f"Черновики писем сформированы. Черновиков создано: {created_batches}.",
                    "items_count": len(item_ids),
                    "supplier_results_count": supplier_results_count,
                    "batches_count": created_batches,
                    "batch_ids": batch_ids,
                    "kp_request_id": kp_request["kp_request_id"] if kp_request else None,
                    "kp_request_code": kp_request["kp_request_code"] if kp_request else None,
                }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка формирования черновиков по реестру: {str(error)}",
        )
    finally:
        conn.close()



@router.get("/registry/kp-requests")
def get_kp_requests(limit: int = 500):
    """Реестр созданных запросов КП: КП00001, КП00002 и т.д."""
    limit = max(1, min(limit, 2000))

    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_registry_columns(cur)
            ensure_kp_request_schema(cur)
            conn.commit()

    return fetch_all(
        """
        SELECT
            kr.kp_request_id,
            kr.kp_request_code,
            kr.status,
            kr.created_at,
            kr.updated_at,
            COALESCE(items.items_count, 0) AS items_count,
            COALESCE(results.supplier_results_count, 0) AS supplier_results_count,
            COALESCE(batches.batches_count, 0) AS batches_count,
            COALESCE(batches.sent_batches_count, 0) AS sent_batches_count,
            COALESCE(batches.error_batches_count, 0) AS error_batches_count,
            COALESCE(logs.sent_logs_count, 0) AS sent_logs_count,
            batches.last_sent_at
        FROM kp_requests kr
        LEFT JOIN (
            SELECT kp_request_id, COUNT(DISTINCT item_id) AS items_count
            FROM kp_request_items
            GROUP BY kp_request_id
        ) items
            ON items.kp_request_id = kr.kp_request_id
        LEFT JOIN (
            SELECT kp_request_id, COUNT(*) AS supplier_results_count
            FROM supplier_search_results
            WHERE kp_request_id IS NOT NULL
            GROUP BY kp_request_id
        ) results
            ON results.kp_request_id = kr.kp_request_id
        LEFT JOIN (
            SELECT
                kp_request_id,
                COUNT(*) AS batches_count,
                COUNT(*) FILTER (WHERE status = 'SENT') AS sent_batches_count,
                COUNT(*) FILTER (WHERE status = 'SEND_ERROR') AS error_batches_count,
                MAX(updated_at) FILTER (WHERE status = 'SENT') AS last_sent_at
            FROM procurement_email_batches
            WHERE kp_request_id IS NOT NULL
            GROUP BY kp_request_id
        ) batches
            ON batches.kp_request_id = kr.kp_request_id
        LEFT JOIN (
            SELECT b.kp_request_id, COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count
            FROM procurement_email_batches b
            LEFT JOIN procurement_email_logs l
                ON l.batch_id = b.batch_id
            WHERE b.kp_request_id IS NOT NULL
            GROUP BY b.kp_request_id
        ) logs
            ON logs.kp_request_id = kr.kp_request_id
        ORDER BY kr.created_at DESC, kr.kp_request_id DESC
        LIMIT %s
        """,
        (limit,),
    )


@router.get("/registry/kp-requests/{kp_request_id}")
def get_kp_request_detail(kp_request_id: int):
    """Детальная карточка запроса КП: позиции, найденные поставщики, черновики."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_registry_columns(cur)
            ensure_kp_request_schema(cur)
            conn.commit()

    request = fetch_one(
        """
        SELECT *
        FROM kp_requests
        WHERE kp_request_id = %s
        """,
        (kp_request_id,),
    )

    if not request:
        raise HTTPException(status_code=404, detail="КП-запрос не найден")

    items = fetch_all(
        """
        SELECT
            kri.kp_request_id,
            a.application_id,
            a.application_no,
            a.application_date,
            a.construction_object,
            COALESCE(NULLIF(a.contract_no, ''), contract_base.contract_no, contract_link.contract_no) AS contract_no,
            COALESCE(a.contract_date::text, contract_base.contract_date::text, contract_link.contract_date) AS contract_date,
            COALESCE(NULLIF(contract_link.contract_appendix, ''), NULLIF(a.contract_appendix, '')) AS contract_appendix,
            i.item_id,
            i.material_id,
            i.okpd2_code_from_application,
            COALESCE(i.okpd2_code_from_application, mom.okpd2_code) AS okpd2_code,
            COALESCE(i.user_group_id_from_application, mugm.id_possition) AS user_group_id,
            i.material_name,
            COALESCE(u.unit_name, i.unit) AS unit,
            i.quantity,
            i.characteristics_comment,
            i.work_doc_code,
            COALESCE(NULLIF(i.work_doc_subject, ''), contract_link.work_doc_subject) AS work_doc_subject,
            i.supply_start_date,
            i.supply_end_date,
            i.processing_status,
            CASE
                WHEN i.supply_start_date IS NOT NULL AND i.supply_end_date IS NOT NULL
                    THEN i.supply_start_date::text || ' — ' || i.supply_end_date::text
                WHEN i.supply_start_date IS NOT NULL
                    THEN i.supply_start_date::text
                WHEN i.supply_end_date IS NOT NULL
                    THEN i.supply_end_date::text
                ELSE NULL
            END AS supply_period
        FROM kp_request_items kri
        JOIN purchase_application_items i
            ON i.item_id = kri.item_id
        JOIN purchase_applications a
            ON a.application_id = i.application_id
        LEFT JOIN material_okpd2_map mom
            ON trim(mom.material_id) = trim(i.material_id)
        AND mom.is_active = true
        LEFT JOIN material_user_group_map mugm
            ON trim(mugm.material_id) = trim(i.material_id)
        LEFT JOIN contracts contract_base
            ON contract_base.contract_id = a.contract_id
        LEFT JOIN LATERAL (
            SELECT
                string_agg(DISTINCT c.contract_no, ', ' ORDER BY c.contract_no) AS contract_no,
                string_agg(DISTINCT c.contract_date::text, ', ' ORDER BY c.contract_date::text) FILTER (WHERE c.contract_date IS NOT NULL) AS contract_date,
                string_agg(DISTINCT l.contract_appendix, ', ' ORDER BY l.contract_appendix) AS contract_appendix,
                string_agg(DISTINCT l.work_doc_subject, ', ' ORDER BY l.work_doc_subject) AS work_doc_subject
            FROM contract_work_doc_subjects l
            JOIN contracts c
                ON c.contract_id = l.contract_id
            WHERE (NULLIF(btrim(a.contract_id), '') IS NULL OR l.contract_id = a.contract_id)
              AND lower(btrim(l.work_doc_code)) = lower(btrim(i.work_doc_code))
              AND (
                    NULLIF(btrim(i.work_doc_subject), '') IS NULL
                    OR lower(btrim(l.work_doc_subject)) = lower(btrim(i.work_doc_subject))
                  )
        ) contract_link ON true
        LEFT JOIN units u
            ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
            OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
        WHERE kri.kp_request_id = %s
        ORDER BY a.application_id, i.source_row_no NULLS LAST, i.item_id
        """,
        (kp_request_id,),
    )

    supplier_results = fetch_all(
        """
        SELECT
            row_number() OVER (
                ORDER BY
                    supplier_name,
                    supplier_inn,
                    search_method,
                    item_id
            ) AS result_no,
            kp_request_id,
            kp_request_code,
            item_id,
            supplier_id,
            supplier_inn,
            supplier_name,
            search_method,
            source_system,
            material_id,
            okpd2_code,
            okved2_code,
            user_group_id,
            match_reason,
            created_at
        FROM supplier_search_results
        WHERE kp_request_id = %s
        ORDER BY search_method, supplier_name, supplier_inn, item_id
        """,
        (kp_request_id,),
    )

    batches = fetch_all(
        """
        SELECT
            b.*,
            s.email AS supplier_email,
            COUNT(DISTINCT bi.item_id) AS items_count,
            COUNT(DISTINCT l.log_id) FILTER (WHERE l.status = 'SENT') AS sent_logs_count,
            MAX(l.sent_at) AS last_sent_at
        FROM procurement_email_batches b
        LEFT JOIN procurement_email_batch_items bi
            ON bi.batch_id = b.batch_id
        LEFT JOIN suppliers s
            ON s.inn = b.supplier_inn
        LEFT JOIN procurement_email_logs l
            ON l.batch_id = b.batch_id
        WHERE b.kp_request_id = %s
        GROUP BY b.batch_id, s.email
        ORDER BY b.search_method, b.supplier_name, b.supplier_inn
        """,
        (kp_request_id,),
    )

    return {
        "request": request,
        "items": items,
        "supplier_results": supplier_results,
        "batches": batches,
    }


@router.get("/{application_id}")
def get_application(application_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_registry_columns(cur)
            conn.commit()

    application = fetch_one(
        """
        SELECT *
        FROM purchase_applications
        WHERE application_id = %s
        """,
        (application_id,),
    )

    if not application:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    items = fetch_all(
        """
        SELECT
            i.*,
            COALESCE(u.unit_name, i.unit) AS unit
        FROM purchase_application_items i
        LEFT JOIN units u
            ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
            OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
        WHERE i.application_id = %s
        ORDER BY i.source_row_no, i.item_id
        """,
        (application_id,),
    )

    return {
        "application": application,
        "items": items,
    }


@router.get("/{application_id}/items")
def get_application_items(application_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_registry_columns(cur)
            conn.commit()

    return fetch_all(
        """
        SELECT
            i.*,
            COALESCE(u.unit_name, i.unit) AS unit
        FROM purchase_application_items i
        LEFT JOIN units u
            ON lower(btrim(u.unit_code)) = lower(btrim(i.unit))
            OR lower(btrim(u.unit_name)) = lower(btrim(i.unit))
        WHERE i.application_id = %s
        ORDER BY i.source_row_no, i.item_id
        """,
        (application_id,),
    )
