# from typing import Optional

# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel

# from app.database import fetch_all, execute, execute_returning, get_connection
# from app.services.audit import log_action
# from app.services.material_okpd2 import ensure_material_okpd2_active_schema
# from app.services.suppliers import ensure_supplier_id_schema
# from app.services.units import ensure_unit_names_storage

# router = APIRouter()


# def prepare_material_okpd2_schema():
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_material_okpd2_active_schema(cur)
#             conn.commit()


# def ensure_user_group_supplier_schema(cur):
#     """Переход mapping'а Группа → Поставщик с ИНН на ID поставщика SUPLXXXXXX."""
#     ensure_supplier_id_schema(cur)


# class MaterialOkpd2Create(BaseModel):
#     material_id: str
#     okpd2_code: str
#     source_comment: Optional[str] = None
#     is_active: bool = False


# class MaterialOkpd2ActiveUpdate(BaseModel):
#     material_id: str
#     okpd2_code: str
#     is_active: bool


# class Okpd2Okved2Create(BaseModel):
#     okpd2_code: str
#     okved2_code: str
#     source_comment: Optional[str] = None


# class MaterialUserGroupCreate(BaseModel):
#     material_id: str
#     user_group_id: str
#     source_comment: Optional[str] = None


# class UserGroupSupplierCreate(BaseModel):
#     user_group_id: str
#     supplier_id: Optional[str] = None
#     supplier_inn: Optional[str] = None
#     source_comment: Optional[str] = None


# @router.get("/options")
# def get_mapping_options():
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_user_group_supplier_schema(cur)
#             conn.commit()

#     return {
#         "materials": fetch_all(
#             """
#             SELECT material_id AS value,
#                    material_id || ' — ' || COALESCE(NULLIF(material_name, ''), 'Не найдено') AS label,
#                    material_name
#             FROM materials
#             ORDER BY material_name
#             """
#         ),
#         "okpd2": fetch_all(
#             """
#             SELECT okpd2_code AS value,
#                    okpd2_code || ' — ' || COALESCE(NULLIF(name_okpd2, ''), 'Не найдено') AS label,
#                    name_okpd2
#             FROM okpd2
#             ORDER BY okpd2_code
#             """
#         ),
#         "okved2": fetch_all(
#             """
#             SELECT okved2_code AS value,
#                    okved2_code || ' — ' || COALESCE(NULLIF(name_okved2, ''), 'Не найдено') AS label,
#                    name_okved2
#             FROM okved2
#             ORDER BY okved2_code
#             """
#         ),
#         "user_groups": fetch_all(
#             """
#             SELECT id_possition AS value,
#                    id_possition || ' — ' || COALESCE(NULLIF(name_possition, ''), 'Не найдено') AS label,
#                    name_possition
#             FROM user_material_groups
#             ORDER BY name_possition
#             """
#         ),
#         "suppliers": fetch_all(
#             """
#             SELECT supplier_id::text AS value,
#                    supplier_id::text || ' - ' ||
#                    COALESCE(NULLIF(name, ''), 'Не найдено') || ' (' ||
#                    COALESCE(NULLIF(inn, ''), 'Не найдено') || ')' AS label,
#                    supplier_id::text AS supplier_id,
#                    inn,
#                    name
#             FROM suppliers
#             ORDER BY name, supplier_id
#             """
#         ),
#     }


# @router.get("/missing/{mapping_type}")
# def get_missing_mappings(mapping_type: str):
#     if mapping_type == "material-okpd2":
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 ensure_unit_names_storage(cur)
#                 conn.commit()
#         return fetch_all(
#             """
#             SELECT
#                 m.material_id,
#                 m.material_name,
#                 COALESCE(u.unit_name, m.unit) AS unit,
#                 m.description
#             FROM materials m
#             LEFT JOIN units u
#                 ON lower(btrim(u.unit_code)) = lower(btrim(m.unit))
#                 OR lower(btrim(u.unit_name)) = lower(btrim(m.unit))
#             WHERE NOT EXISTS (
#                 SELECT 1
#                 FROM material_okpd2_map mom
#                 WHERE btrim(mom.material_id) = btrim(m.material_id)
#                 AND mom.is_active = true
#             )
#             ORDER BY m.material_name, m.material_id
#             """
#         )

#     if mapping_type == "okpd2-okved2":
#         return fetch_all(
#             """
#             SELECT
#                 btrim(o.okpd2_code) AS okpd2_code,
#                 MAX(o.name_okpd2) AS name_okpd2
#             FROM okpd2 o
#             JOIN material_okpd2_map mom
#                 ON btrim(mom.okpd2_code) = btrim(o.okpd2_code)
#             AND mom.is_active = true
#             WHERE NOT EXISTS (
#                 SELECT 1
#                 FROM okpd2_okved2_map oom
#                 WHERE btrim(oom.okpd2_code) = btrim(o.okpd2_code)
#             )
#             GROUP BY btrim(o.okpd2_code)
#             ORDER BY btrim(o.okpd2_code)
#             """
#         )

#     if mapping_type == "material-user-group":
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 ensure_unit_names_storage(cur)
#                 conn.commit()
#         return fetch_all(
#             """
#             SELECT
#                 m.material_id,
#                 m.material_name,
#                 COALESCE(u.unit_name, m.unit) AS unit,
#                 m.description
#             FROM materials m
#             LEFT JOIN units u
#                 ON lower(btrim(u.unit_code)) = lower(btrim(m.unit))
#                 OR lower(btrim(u.unit_name)) = lower(btrim(m.unit))
#             WHERE NOT EXISTS (
#                 SELECT 1
#                 FROM material_user_group_map mugm
#                 WHERE mugm.material_id = m.material_id
#             )
#             ORDER BY m.material_name, m.material_id
#             """
#         )

#     if mapping_type == "user-group-supplier":
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 ensure_user_group_supplier_schema(cur)
#                 conn.commit()
#         return fetch_all(
#             """
#             SELECT
#                 g.id_possition AS user_group_id,
#                 g.name_possition AS user_group_name,
#                 g.description
#             FROM user_material_groups g
#             WHERE NOT EXISTS (
#                 SELECT 1
#                 FROM user_group_supply_map ugsm
#                 WHERE ugsm.user_group_id = g.id_possition
#                   AND COALESCE(NULLIF(ugsm.supplier_id::text, ''), NULLIF(ugsm.inn_supply, '')) IS NOT NULL
#             )
#             ORDER BY g.name_possition, g.id_possition
#             """
#         )

#     raise HTTPException(status_code=404, detail="Неизвестный тип mapping")


# @router.get("/material-okpd2")
# def get_material_okpd2():
#     prepare_material_okpd2_schema()

#     return fetch_all(
#         """
#         SELECT
#             mom.material_id,
#             m.material_name,
#             mom.okpd2_code,
#             o.name_okpd2,
#             COALESCE(mom.is_active, false) AS is_active,
#             mom.source_comment
#         FROM material_okpd2_map mom
#         JOIN materials m
#             ON btrim(m.material_id) = btrim(mom.material_id)
#         JOIN okpd2 o
#             ON btrim(o.okpd2_code) = btrim(mom.okpd2_code)
#         ORDER BY
#             m.material_name,
#             COALESCE(mom.is_active, false) DESC,
#             mom.okpd2_code
#         """
#     )


# @router.post("/material-okpd2")
# def create_material_okpd2(p: MaterialOkpd2Create):
#     try:
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 ensure_material_okpd2_active_schema(cur)

#                 cur.execute(
#                     """
#                     SELECT EXISTS (
#                         SELECT 1
#                         FROM material_okpd2_map
#                         WHERE btrim(material_id) = btrim(%s)
#                           AND is_active = true
#                     ) AS has_active
#                     """,
#                     (p.material_id,),
#                 )
#                 has_active = cur.fetchone()["has_active"]
#                 should_activate = bool(p.is_active) or not has_active

#                 cur.execute(
#                     """
#                     INSERT INTO material_okpd2_map (
#                         material_id,
#                         okpd2_code,
#                         source_comment,
#                         is_active
#                     )
#                     VALUES (%s,%s,%s,false)
#                     RETURNING material_id, okpd2_code, source_comment, is_active
#                     """,
#                     (p.material_id, p.okpd2_code, p.source_comment),
#                 )
#                 row = cur.fetchone()

#                 if should_activate:
#                     cur.execute(
#                         """
#                         UPDATE material_okpd2_map
#                         SET is_active = false
#                         WHERE btrim(material_id) = btrim(%s)
#                         """,
#                         (p.material_id,),
#                     )
#                     cur.execute(
#                         """
#                         UPDATE material_okpd2_map
#                         SET is_active = true
#                         WHERE btrim(material_id) = btrim(%s)
#                           AND btrim(okpd2_code) = btrim(%s)
#                         """,
#                         (p.material_id, p.okpd2_code),
#                     )

#                 log_action(cur, "mapping", f"material-okpd2:{p.material_id}:{p.okpd2_code}", "CREATE", dict(row or {}))
#                 conn.commit()

#         return get_material_okpd2()
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))


# @router.delete("/material-okpd2")
# def delete_material_okpd2(material_id: str, okpd2_code: str):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(
#                 "DELETE FROM material_okpd2_map WHERE material_id=%s AND okpd2_code=%s",
#                 (material_id, okpd2_code),
#             )
#             log_action(cur, "mapping", f"material-okpd2:{material_id}:{okpd2_code}", "DELETE", {"material_id": material_id, "okpd2_code": okpd2_code})
#             conn.commit()
#     return {"status": "OK"}


# @router.patch("/material-okpd2/active")
# def update_material_okpd2_active(p: MaterialOkpd2ActiveUpdate):
#     if not p.is_active:
#         raise HTTPException(
#             status_code=400,
#             detail="Нельзя снять активную связь без выбора новой. Выберите другой ОКПД2 как активный для этого материала.",
#         )

#     try:
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 ensure_material_okpd2_active_schema(cur)

#                 material_id = str(p.material_id or "").strip()
#                 okpd2_code = str(p.okpd2_code or "").strip()

#                 if not material_id or not okpd2_code:
#                     raise HTTPException(status_code=400, detail="Не передан material_id или okpd2_code")

#                 cur.execute(
#                     """
#                     SELECT 1
#                     FROM material_okpd2_map
#                     WHERE btrim(material_id) = btrim(%s)
#                       AND btrim(okpd2_code) = btrim(%s)
#                     """,
#                     (material_id, okpd2_code),
#                 )

#                 if not cur.fetchone():
#                     raise HTTPException(status_code=404, detail="Связь Material → OKPD2 не найдена")

#                 cur.execute(
#                     """
#                     UPDATE material_okpd2_map
#                     SET is_active = false
#                     WHERE btrim(material_id) = btrim(%s)
#                     """,
#                     (material_id,),
#                 )
#                 cur.execute(
#                     """
#                     UPDATE material_okpd2_map
#                     SET is_active = true
#                     WHERE btrim(material_id) = btrim(%s)
#                       AND btrim(okpd2_code) = btrim(%s)
#                     """,
#                     (material_id, okpd2_code),
#                 )

#                 cur.execute(
#                     """
#                     SELECT
#                         mom.material_id,
#                         m.material_name,
#                         mom.okpd2_code,
#                         o.name_okpd2,
#                         COALESCE(mom.is_active, false) AS is_active,
#                         CASE
#                             WHEN COALESCE(mom.is_active, false) THEN 'Да'
#                             ELSE 'Нет'
#                         END AS active_link,
#                         mom.source_comment
#                     FROM material_okpd2_map mom
#                     JOIN materials m
#                         ON btrim(m.material_id) = btrim(mom.material_id)
#                     JOIN okpd2 o
#                         ON btrim(o.okpd2_code) = btrim(mom.okpd2_code)
#                     WHERE btrim(mom.material_id) = btrim(%s)
#                       AND btrim(mom.okpd2_code) = btrim(%s)
#                     LIMIT 1
#                     """,
#                     (material_id, okpd2_code),
#                 )
#                 updated_row = cur.fetchone()
#                 log_action(cur, "mapping", f"material-okpd2:{material_id}:{okpd2_code}", "ACTIVATE", dict(updated_row or {}))
#                 conn.commit()

#         return {"status": "OK", "row": updated_row}
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))


# @router.get("/okpd2-okved2")
# def get_okpd2_okved2():
#     return fetch_all(
#         """
#         SELECT
#             oom.okpd2_code,
#             o2.name_okpd2,
#             oom.okved2_code,
#             ov.name_okved2,
#             oom.source_comment
#         FROM okpd2_okved2_map oom
#         JOIN okpd2 o2 ON o2.okpd2_code = oom.okpd2_code
#         JOIN okved2 ov ON ov.okved2_code = oom.okved2_code
#         ORDER BY oom.okpd2_code, oom.okved2_code
#         """
#     )


# @router.post("/okpd2-okved2")
# def create_okpd2_okved2(p: Okpd2Okved2Create):
#     try:
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 cur.execute(
#                     """
#                     INSERT INTO okpd2_okved2_map (okpd2_code, okved2_code, source_comment)
#                     VALUES (%s,%s,%s)
#                     RETURNING okpd2_code, okved2_code, source_comment
#                     """,
#                     (p.okpd2_code, p.okved2_code, p.source_comment),
#                 )
#                 row = cur.fetchone()
#                 log_action(cur, "mapping", f"okpd2-okved2:{p.okpd2_code}:{p.okved2_code}", "CREATE", dict(row or {}))
#                 conn.commit()
#                 return row
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))


# @router.delete("/okpd2-okved2")
# def delete_okpd2_okved2(okpd2_code: str, okved2_code: str):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(
#                 "DELETE FROM okpd2_okved2_map WHERE okpd2_code=%s AND okved2_code=%s",
#                 (okpd2_code, okved2_code),
#             )
#             log_action(cur, "mapping", f"okpd2-okved2:{okpd2_code}:{okved2_code}", "DELETE", {"okpd2_code": okpd2_code, "okved2_code": okved2_code})
#             conn.commit()
#     return {"status": "OK"}


# @router.get("/material-user-group")
# def get_material_user_group():
#     return fetch_all(
#         """
#         SELECT
#             mugm.material_id,
#             m.material_name,
#             mugm.id_possition AS user_group_id,
#             g.name_possition AS user_group_name,
#             mugm.source_comment
#         FROM material_user_group_map mugm
#         JOIN materials m ON m.material_id = mugm.material_id
#         JOIN user_material_groups g ON g.id_possition = mugm.id_possition
#         ORDER BY m.material_name, g.name_possition
#         """
#     )


# @router.post("/material-user-group")
# def create_material_user_group(p: MaterialUserGroupCreate):
#     try:
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 cur.execute(
#                     """
#                     INSERT INTO material_user_group_map (material_id, id_possition, source_comment)
#                     VALUES (%s,%s,%s)
#                     RETURNING material_id, id_possition AS user_group_id, source_comment
#                     """,
#                     (p.material_id, p.user_group_id, p.source_comment),
#                 )
#                 row = cur.fetchone()
#                 log_action(cur, "mapping", f"material-user-group:{p.material_id}:{p.user_group_id}", "CREATE", dict(row or {}))
#                 conn.commit()
#                 return row
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))


# @router.delete("/material-user-group")
# def delete_material_user_group(material_id: str, user_group_id: str):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute(
#                 """
#                 DELETE FROM material_user_group_map
#                 WHERE material_id = %s
#                   AND id_possition = %s
#                 """,
#                 (material_id, user_group_id),
#             )
#             log_action(cur, "mapping", f"material-user-group:{material_id}:{user_group_id}", "DELETE", {"material_id": material_id, "user_group_id": user_group_id})
#             conn.commit()
#     return {"status": "OK"}


# @router.get("/user-group-supplier")
# def get_user_group_supplier():
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_user_group_supplier_schema(cur)
#             conn.commit()

#     return fetch_all(
#         """
#         SELECT DISTINCT ON (ugsm.user_group_id, COALESCE(ugsm.supplier_id::text, s.supplier_id::text, ugsm.inn_supply))
#             ugsm.user_group_id,
#             g.name_possition AS user_group_name,
#             COALESCE(ugsm.supplier_id::text, s.supplier_id::text) AS supplier_id,
#             COALESCE(s.inn, ugsm.inn_supply) AS supplier_inn,
#             COALESCE(NULLIF(s.name, ''), 'Не найдено') AS name_supply,
#             ugsm.source_comment
#         FROM user_group_supply_map ugsm
#         JOIN user_material_groups g ON g.id_possition = ugsm.user_group_id
#         LEFT JOIN suppliers s
#             ON s.supplier_id::text = ugsm.supplier_id::text
#             OR ((ugsm.supplier_id IS NULL OR btrim(ugsm.supplier_id::text) = '') AND btrim(s.inn) = btrim(ugsm.inn_supply))
#         ORDER BY ugsm.user_group_id, COALESCE(ugsm.supplier_id::text, s.supplier_id::text, ugsm.inn_supply), g.name_possition, s.name
#         """
#     )


# @router.post("/user-group-supplier")
# def create_user_group_supplier(p: UserGroupSupplierCreate):
#     supplier_key = str(p.supplier_id or p.supplier_inn or "").strip()

#     if not supplier_key:
#         raise HTTPException(status_code=400, detail="Выберите поставщика")

#     try:
#         with get_connection() as conn:
#             with conn.cursor() as cur:
#                 ensure_user_group_supplier_schema(cur)
#                 cur.execute(
#                     """
#                     SELECT supplier_id::text AS supplier_id, inn, name
#                     FROM suppliers
#                     WHERE supplier_id::text = %s OR btrim(inn) = btrim(%s)
#                     ORDER BY CASE WHEN supplier_id::text = %s THEN 0 ELSE 1 END
#                     LIMIT 1
#                     """,
#                     (supplier_key, supplier_key, supplier_key),
#                 )
#                 supplier = cur.fetchone()

#                 if not supplier:
#                     raise HTTPException(status_code=400, detail="Поставщик не найден в справочнике поставщиков")

#                 cur.execute(
#                     """
#                     INSERT INTO user_group_supply_map (user_group_id, supplier_id, inn_supply, source_comment)
#                     VALUES (%s,%s,%s,%s)
#                     RETURNING user_group_id, supplier_id::text AS supplier_id, inn_supply AS supplier_inn, source_comment
#                     """,
#                     (p.user_group_id, supplier["supplier_id"], supplier.get("inn"), p.source_comment),
#                 )
#                 row = cur.fetchone()
#                 log_action(cur, "mapping", f"user-group-supplier:{p.user_group_id}:{supplier['supplier_id']}", "CREATE", dict(row or {}))
#                 conn.commit()
#                 return row
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))


# @router.delete("/user-group-supplier")
# def delete_user_group_supplier(user_group_id: str, supplier_id: Optional[str] = None, inn_supply: Optional[str] = None):
#     supplier_key = str(supplier_id or inn_supply or "").strip()

#     if not supplier_key:
#         raise HTTPException(status_code=400, detail="Не передан ID поставщика")

#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             ensure_user_group_supplier_schema(cur)
#             cur.execute(
#                 """
#                 DELETE FROM user_group_supply_map
#                 WHERE user_group_id = %s
#                   AND (
#                     supplier_id::text = %s
#                     OR (COALESCE(NULLIF(supplier_id::text, ''), '') = '' AND inn_supply = %s)
#                   )
#                 """,
#                 (user_group_id, supplier_key, supplier_key),
#             )
#             log_action(cur, "mapping", f"user-group-supplier:{user_group_id}:{supplier_key}", "DELETE", {"user_group_id": user_group_id, "supplier_id": supplier_key})
#             conn.commit()
#     return {"status": "OK"}

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import fetch_all, get_connection
from app.services.audit import log_action
from app.services.material_okpd2 import ensure_material_okpd2_active_schema
from app.services.units import ensure_unit_names_storage

router = APIRouter()


def prepare_material_okpd2_schema():
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_material_okpd2_active_schema(cur)
            conn.commit()


def ensure_user_group_supplier_schema(cur):
    """
    Актуальная структура user_group_supply_map:
      - user_group_id text NOT NULL
      - supplier_id text NOT NULL
      - source_comment text NULL

    Связь Группа материалов → Поставщик строится только по supplier_id.
    inn_supply больше не используется и не должен упоминаться в SQL.
    """
    cur.execute(
        """
        ALTER TABLE user_group_supply_map
        ADD COLUMN IF NOT EXISTS supplier_id text
        """
    )

    cur.execute(
        """
        ALTER TABLE user_group_supply_map
        ADD COLUMN IF NOT EXISTS source_comment text
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_group_supply_map_supplier_id
        ON user_group_supply_map(supplier_id)
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_group_supply_map_user_group_id
        ON user_group_supply_map(user_group_id)
        """
    )


class MaterialOkpd2Create(BaseModel):
    material_id: str
    okpd2_code: str
    source_comment: Optional[str] = None
    is_active: bool = False


class MaterialOkpd2ActiveUpdate(BaseModel):
    material_id: str
    okpd2_code: str
    is_active: bool


class Okpd2Okved2Create(BaseModel):
    okpd2_code: str
    okved2_code: str
    source_comment: Optional[str] = None


class MaterialUserGroupCreate(BaseModel):
    material_id: str
    user_group_id: str
    source_comment: Optional[str] = None


class UserGroupSupplierCreate(BaseModel):
    user_group_id: str
    supplier_id: str
    source_comment: Optional[str] = None


@router.get("/options")
def get_mapping_options():
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_user_group_supplier_schema(cur)
            conn.commit()

    return {
        "materials": fetch_all(
            """
            SELECT
                material_id AS value,
                material_id || ' — ' || COALESCE(NULLIF(material_name, ''), 'Не найдено') AS label,
                material_name
            FROM materials
            ORDER BY material_name
            """
        ),
        "okpd2": fetch_all(
            """
            SELECT
                okpd2_code AS value,
                okpd2_code || ' — ' || COALESCE(NULLIF(name_okpd2, ''), 'Не найдено') AS label,
                name_okpd2
            FROM okpd2
            ORDER BY okpd2_code
            """
        ),
        "okved2": fetch_all(
            """
            SELECT
                okved2_code AS value,
                okved2_code || ' — ' || COALESCE(NULLIF(name_okved2, ''), 'Не найдено') AS label,
                name_okved2
            FROM okved2
            ORDER BY okved2_code
            """
        ),
        "user_groups": fetch_all(
            """
            SELECT
                id_possition AS value,
                id_possition || ' — ' || COALESCE(NULLIF(name_possition, ''), 'Не найдено') AS label,
                name_possition
            FROM user_material_groups
            ORDER BY name_possition
            """
        ),
        "suppliers": fetch_all(
            """
            SELECT
                supplier_id::text AS value,
                supplier_id::text || ' — ' ||
                    COALESCE(NULLIF(name, ''), 'Не найдено') || ' (' ||
                    COALESCE(NULLIF(inn, ''), 'ИНН не указан') || ')' AS label,
                supplier_id::text AS supplier_id,
                inn,
                name
            FROM suppliers
            ORDER BY name, supplier_id
            """
        ),
    }


@router.get("/missing/{mapping_type}")
def get_missing_mappings(mapping_type: str):
    if mapping_type == "material-okpd2":
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_unit_names_storage(cur)
                conn.commit()

        return fetch_all(
            """
            SELECT
                m.material_id,
                m.material_name,
                COALESCE(u.unit_name, m.unit) AS unit,
                m.description
            FROM materials m
            LEFT JOIN units u
                ON lower(btrim(u.unit_code)) = lower(btrim(m.unit))
                OR lower(btrim(u.unit_name)) = lower(btrim(m.unit))
            WHERE NOT EXISTS (
                SELECT 1
                FROM material_okpd2_map mom
                WHERE btrim(mom.material_id) = btrim(m.material_id)
                  AND mom.is_active = true
            )
            ORDER BY m.material_name, m.material_id
            """
        )

    if mapping_type == "okpd2-okved2":
        return fetch_all(
            """
            SELECT
                btrim(o.okpd2_code) AS okpd2_code,
                MAX(o.name_okpd2) AS name_okpd2
            FROM okpd2 o
            JOIN material_okpd2_map mom
                ON btrim(mom.okpd2_code) = btrim(o.okpd2_code)
               AND mom.is_active = true
            WHERE NOT EXISTS (
                SELECT 1
                FROM okpd2_okved2_map oom
                WHERE btrim(oom.okpd2_code) = btrim(o.okpd2_code)
            )
            GROUP BY btrim(o.okpd2_code)
            ORDER BY btrim(o.okpd2_code)
            """
        )

    if mapping_type == "material-user-group":
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_unit_names_storage(cur)
                conn.commit()

        return fetch_all(
            """
            SELECT
                m.material_id,
                m.material_name,
                COALESCE(u.unit_name, m.unit) AS unit,
                m.description
            FROM materials m
            LEFT JOIN units u
                ON lower(btrim(u.unit_code)) = lower(btrim(m.unit))
                OR lower(btrim(u.unit_name)) = lower(btrim(m.unit))
            WHERE NOT EXISTS (
                SELECT 1
                FROM material_user_group_map mugm
                WHERE mugm.material_id = m.material_id
            )
            ORDER BY m.material_name, m.material_id
            """
        )

    if mapping_type == "user-group-supplier":
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_user_group_supplier_schema(cur)
                conn.commit()

        return fetch_all(
            """
            SELECT
                g.id_possition AS user_group_id,
                g.name_possition AS user_group_name,
                g.description
            FROM user_material_groups g
            WHERE NOT EXISTS (
                SELECT 1
                FROM user_group_supply_map ugsm
                WHERE ugsm.user_group_id = g.id_possition
                  AND ugsm.supplier_id IS NOT NULL
                  AND btrim(ugsm.supplier_id) <> ''
            )
            ORDER BY g.name_possition, g.id_possition
            """
        )

    raise HTTPException(status_code=404, detail="Неизвестный тип mapping")


@router.get("/material-okpd2")
def get_material_okpd2():
    prepare_material_okpd2_schema()

    return fetch_all(
        """
        SELECT
            mom.material_id,
            m.material_name,
            mom.okpd2_code,
            o.name_okpd2,
            COALESCE(mom.is_active, false) AS is_active,
            mom.source_comment
        FROM material_okpd2_map mom
        JOIN materials m
            ON btrim(m.material_id) = btrim(mom.material_id)
        JOIN okpd2 o
            ON btrim(o.okpd2_code) = btrim(mom.okpd2_code)
        ORDER BY
            m.material_name,
            COALESCE(mom.is_active, false) DESC,
            mom.okpd2_code
        """
    )


@router.post("/material-okpd2")
def create_material_okpd2(p: MaterialOkpd2Create):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_material_okpd2_active_schema(cur)

                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM material_okpd2_map
                        WHERE btrim(material_id) = btrim(%s)
                          AND is_active = true
                    ) AS has_active
                    """,
                    (p.material_id,),
                )
                has_active = cur.fetchone()["has_active"]
                should_activate = bool(p.is_active) or not has_active

                cur.execute(
                    """
                    INSERT INTO material_okpd2_map (
                        material_id,
                        okpd2_code,
                        source_comment,
                        is_active
                    )
                    VALUES (%s,%s,%s,false)
                    RETURNING material_id, okpd2_code, source_comment, is_active
                    """,
                    (p.material_id, p.okpd2_code, p.source_comment),
                )
                row = cur.fetchone()

                if should_activate:
                    cur.execute(
                        """
                        UPDATE material_okpd2_map
                        SET is_active = false
                        WHERE btrim(material_id) = btrim(%s)
                        """,
                        (p.material_id,),
                    )
                    cur.execute(
                        """
                        UPDATE material_okpd2_map
                        SET is_active = true
                        WHERE btrim(material_id) = btrim(%s)
                          AND btrim(okpd2_code) = btrim(%s)
                        """,
                        (p.material_id, p.okpd2_code),
                    )

                log_action(
                    cur,
                    "mapping",
                    f"material-okpd2:{p.material_id}:{p.okpd2_code}",
                    "CREATE",
                    dict(row or {}),
                )
                conn.commit()

        return get_material_okpd2()

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/material-okpd2")
def delete_material_okpd2(material_id: str, okpd2_code: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM material_okpd2_map
                WHERE material_id = %s
                  AND okpd2_code = %s
                """,
                (material_id, okpd2_code),
            )
            log_action(
                cur,
                "mapping",
                f"material-okpd2:{material_id}:{okpd2_code}",
                "DELETE",
                {"material_id": material_id, "okpd2_code": okpd2_code},
            )
            conn.commit()

    return {"status": "OK"}


@router.patch("/material-okpd2/active")
def update_material_okpd2_active(p: MaterialOkpd2ActiveUpdate):
    if not p.is_active:
        raise HTTPException(
            status_code=400,
            detail="Нельзя снять активную связь без выбора новой. Выберите другой ОКПД2 как активный для этого материала.",
        )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_material_okpd2_active_schema(cur)

                material_id = str(p.material_id or "").strip()
                okpd2_code = str(p.okpd2_code or "").strip()

                if not material_id or not okpd2_code:
                    raise HTTPException(status_code=400, detail="Не передан material_id или okpd2_code")

                cur.execute(
                    """
                    SELECT 1
                    FROM material_okpd2_map
                    WHERE btrim(material_id) = btrim(%s)
                      AND btrim(okpd2_code) = btrim(%s)
                    """,
                    (material_id, okpd2_code),
                )

                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Связь Material → OKPD2 не найдена")

                cur.execute(
                    """
                    UPDATE material_okpd2_map
                    SET is_active = false
                    WHERE btrim(material_id) = btrim(%s)
                    """,
                    (material_id,),
                )
                cur.execute(
                    """
                    UPDATE material_okpd2_map
                    SET is_active = true
                    WHERE btrim(material_id) = btrim(%s)
                      AND btrim(okpd2_code) = btrim(%s)
                    """,
                    (material_id, okpd2_code),
                )

                cur.execute(
                    """
                    SELECT
                        mom.material_id,
                        m.material_name,
                        mom.okpd2_code,
                        o.name_okpd2,
                        COALESCE(mom.is_active, false) AS is_active,
                        CASE
                            WHEN COALESCE(mom.is_active, false) THEN 'Да'
                            ELSE 'Нет'
                        END AS active_link,
                        mom.source_comment
                    FROM material_okpd2_map mom
                    JOIN materials m
                        ON btrim(m.material_id) = btrim(mom.material_id)
                    JOIN okpd2 o
                        ON btrim(o.okpd2_code) = btrim(mom.okpd2_code)
                    WHERE btrim(mom.material_id) = btrim(%s)
                      AND btrim(mom.okpd2_code) = btrim(%s)
                    LIMIT 1
                    """,
                    (material_id, okpd2_code),
                )
                updated_row = cur.fetchone()

                log_action(
                    cur,
                    "mapping",
                    f"material-okpd2:{material_id}:{okpd2_code}",
                    "ACTIVATE",
                    dict(updated_row or {}),
                )
                conn.commit()

        return {"status": "OK", "row": updated_row}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/okpd2-okved2")
def get_okpd2_okved2():
    return fetch_all(
        """
        SELECT
            oom.okpd2_code,
            o2.name_okpd2,
            oom.okved2_code,
            ov.name_okved2,
            oom.source_comment
        FROM okpd2_okved2_map oom
        JOIN okpd2 o2
            ON o2.okpd2_code = oom.okpd2_code
        JOIN okved2 ov
            ON ov.okved2_code = oom.okved2_code
        ORDER BY oom.okpd2_code, oom.okved2_code
        """
    )


@router.post("/okpd2-okved2")
def create_okpd2_okved2(p: Okpd2Okved2Create):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO okpd2_okved2_map (
                        okpd2_code,
                        okved2_code,
                        source_comment
                    )
                    VALUES (%s,%s,%s)
                    RETURNING okpd2_code, okved2_code, source_comment
                    """,
                    (p.okpd2_code, p.okved2_code, p.source_comment),
                )
                row = cur.fetchone()

                log_action(
                    cur,
                    "mapping",
                    f"okpd2-okved2:{p.okpd2_code}:{p.okved2_code}",
                    "CREATE",
                    dict(row or {}),
                )
                conn.commit()

                return row

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/okpd2-okved2")
def delete_okpd2_okved2(okpd2_code: str, okved2_code: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM okpd2_okved2_map
                WHERE okpd2_code = %s
                  AND okved2_code = %s
                """,
                (okpd2_code, okved2_code),
            )
            log_action(
                cur,
                "mapping",
                f"okpd2-okved2:{okpd2_code}:{okved2_code}",
                "DELETE",
                {"okpd2_code": okpd2_code, "okved2_code": okved2_code},
            )
            conn.commit()

    return {"status": "OK"}


@router.get("/material-user-group")
def get_material_user_group():
    return fetch_all(
        """
        SELECT
            mugm.material_id,
            m.material_name,
            mugm.id_possition AS user_group_id,
            g.name_possition AS user_group_name,
            mugm.source_comment
        FROM material_user_group_map mugm
        JOIN materials m
            ON m.material_id = mugm.material_id
        JOIN user_material_groups g
            ON g.id_possition = mugm.id_possition
        ORDER BY m.material_name, g.name_possition
        """
    )


@router.post("/material-user-group")
def create_material_user_group(p: MaterialUserGroupCreate):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO material_user_group_map (
                        material_id,
                        id_possition,
                        source_comment
                    )
                    VALUES (%s,%s,%s)
                    RETURNING material_id, id_possition AS user_group_id, source_comment
                    """,
                    (p.material_id, p.user_group_id, p.source_comment),
                )
                row = cur.fetchone()

                log_action(
                    cur,
                    "mapping",
                    f"material-user-group:{p.material_id}:{p.user_group_id}",
                    "CREATE",
                    dict(row or {}),
                )
                conn.commit()

                return row

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/material-user-group")
def delete_material_user_group(material_id: str, user_group_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM material_user_group_map
                WHERE material_id = %s
                  AND id_possition = %s
                """,
                (material_id, user_group_id),
            )
            log_action(
                cur,
                "mapping",
                f"material-user-group:{material_id}:{user_group_id}",
                "DELETE",
                {"material_id": material_id, "user_group_id": user_group_id},
            )
            conn.commit()

    return {"status": "OK"}


@router.get("/user-group-supplier")
def get_user_group_supplier():
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_user_group_supplier_schema(cur)
            conn.commit()

    return fetch_all(
        """
        SELECT
            ugsm.user_group_id,
            g.name_possition AS user_group_name,
            ugsm.supplier_id,
            s.inn AS supplier_inn,
            COALESCE(NULLIF(s.name, ''), 'Не найдено') AS name_supply,
            COALESCE(NULLIF(s.short_name, ''), NULLIF(s.name, ''), 'Не найдено') AS supplier_short_name,
            ugsm.source_comment
        FROM user_group_supply_map ugsm
        JOIN user_material_groups g
            ON g.id_possition = ugsm.user_group_id
        JOIN suppliers s
            ON s.supplier_id = ugsm.supplier_id
        ORDER BY g.name_possition, s.name, ugsm.supplier_id
        """
    )


@router.post("/user-group-supplier")
def create_user_group_supplier(p: UserGroupSupplierCreate):
    user_group_id = str(p.user_group_id or "").strip()
    supplier_id = str(p.supplier_id or "").strip()

    if not user_group_id:
        raise HTTPException(status_code=400, detail="Выберите группу материалов")

    if not supplier_id:
        raise HTTPException(status_code=400, detail="Выберите поставщика")

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_user_group_supplier_schema(cur)

                cur.execute(
                    """
                    SELECT supplier_id, inn, name
                    FROM suppliers
                    WHERE supplier_id = %s
                    LIMIT 1
                    """,
                    (supplier_id,),
                )
                supplier = cur.fetchone()

                if not supplier:
                    raise HTTPException(status_code=400, detail="Поставщик не найден в справочнике поставщиков")

                cur.execute(
                    """
                    SELECT id_possition
                    FROM user_material_groups
                    WHERE id_possition = %s
                    LIMIT 1
                    """,
                    (user_group_id,),
                )
                user_group = cur.fetchone()

                if not user_group:
                    raise HTTPException(status_code=400, detail="Группа материалов не найдена в справочнике групп")

                cur.execute(
                    """
                    INSERT INTO user_group_supply_map (
                        user_group_id,
                        supplier_id,
                        source_comment
                    )
                    VALUES (%s,%s,%s)
                    ON CONFLICT (user_group_id, supplier_id)
                    DO UPDATE SET
                        source_comment = EXCLUDED.source_comment
                    RETURNING user_group_id, supplier_id, source_comment
                    """,
                    (user_group_id, supplier_id, p.source_comment),
                )
                row = cur.fetchone()

                log_action(
                    cur,
                    "mapping",
                    f"user-group-supplier:{user_group_id}:{supplier_id}",
                    "CREATE",
                    {
                        **dict(row or {}),
                        "supplier_inn": supplier.get("inn"),
                        "supplier_name": supplier.get("name"),
                    },
                )
                conn.commit()

                return {
                    **dict(row or {}),
                    "supplier_inn": supplier.get("inn"),
                    "name_supply": supplier.get("name"),
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/user-group-supplier")
def delete_user_group_supplier(user_group_id: str, supplier_id: str):
    user_group_id = str(user_group_id or "").strip()
    supplier_id = str(supplier_id or "").strip()

    if not user_group_id:
        raise HTTPException(status_code=400, detail="Не передана группа материалов")

    if not supplier_id:
        raise HTTPException(status_code=400, detail="Не передан ID поставщика")

    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_user_group_supplier_schema(cur)

            cur.execute(
                """
                DELETE FROM user_group_supply_map
                WHERE user_group_id = %s
                  AND supplier_id = %s
                """,
                (user_group_id, supplier_id),
            )

            log_action(
                cur,
                "mapping",
                f"user-group-supplier:{user_group_id}:{supplier_id}",
                "DELETE",
                {"user_group_id": user_group_id, "supplier_id": supplier_id},
            )
            conn.commit()

    return {"status": "OK"}
