from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import fetch_all, execute, execute_returning

router = APIRouter()


class MaterialOkpd2Create(BaseModel):
    material_id: str
    okpd2_code: str
    source_comment: Optional[str] = None


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
    supplier_inn: str
    source_comment: Optional[str] = None


@router.get("/options")
def get_mapping_options():
    return {
        "materials": fetch_all(
            """
            SELECT material_id AS value,
                   material_id || ' — ' || material_name AS label,
                   material_name
            FROM materials
            ORDER BY material_name
            """
        ),
        "okpd2": fetch_all(
            """
            SELECT okpd2_code AS value,
                   okpd2_code || ' — ' || COALESCE(name_okpd2, '') AS label,
                   name_okpd2
            FROM okpd2
            ORDER BY okpd2_code
            """
        ),
        "okved2": fetch_all(
            """
            SELECT okved2_code AS value,
                   okved2_code || ' — ' || COALESCE(name_okved2, '') AS label,
                   name_okved2
            FROM okved2
            ORDER BY okved2_code
            """
        ),
        "user_groups": fetch_all(
            """
            SELECT id_possition AS value,
                   id_possition || ' — ' || name_possition AS label,
                   name_possition
            FROM user_material_groups
            ORDER BY name_possition
            """
        ),
        "suppliers": fetch_all(
            """
            SELECT inn AS value,
                   inn || ' — ' || name AS label,
                   supplier_id,
                   name
            FROM suppliers
            ORDER BY name, inn
            """
        ),
    }
@router.get("/missing/{mapping_type}")
def get_missing_mappings(mapping_type: str):
    if mapping_type == "material-okpd2":
        return fetch_all(
            """
            SELECT
                m.material_id,
                m.material_name,
                m.unit,
                m.description
            FROM materials m
            WHERE NOT EXISTS (
                SELECT 1
                FROM material_okpd2_map mom
                WHERE mom.material_id = m.material_id
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
        return fetch_all(
            """
            SELECT
                m.material_id,
                m.material_name,
                m.unit,
                m.description
            FROM materials m
            WHERE NOT EXISTS (
                SELECT 1
                FROM material_user_group_map mugm
                WHERE mugm.material_id = m.material_id
            )
            ORDER BY m.material_name, m.material_id
            """
        )

    if mapping_type == "user-group-supplier":
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
            )
            ORDER BY g.name_possition, g.id_possition
            """
        )

    raise HTTPException(status_code=404, detail="Неизвестный тип mapping")

@router.get("/material-okpd2")
def get_material_okpd2():
    return fetch_all(
        """
        SELECT
            mom.material_id,
            m.material_name,
            mom.okpd2_code,
            o.name_okpd2,
            mom.source_comment
        FROM material_okpd2_map mom
        JOIN materials m ON m.material_id = mom.material_id
        JOIN okpd2 o ON o.okpd2_code = mom.okpd2_code
        ORDER BY m.material_name, mom.okpd2_code
        """
    )


@router.post("/material-okpd2")
def create_material_okpd2(p: MaterialOkpd2Create):
    try:
        return execute_returning(
            """
            INSERT INTO material_okpd2_map (material_id, okpd2_code, source_comment)
            VALUES (%s,%s,%s)
            RETURNING material_id, okpd2_code, source_comment
            """,
            (p.material_id, p.okpd2_code, p.source_comment),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/material-okpd2")
def delete_material_okpd2(material_id: str, okpd2_code: str):
    execute(
        "DELETE FROM material_okpd2_map WHERE material_id=%s AND okpd2_code=%s",
        (material_id, okpd2_code),
    )
    return {"status": "OK"}


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
        JOIN okpd2 o2 ON o2.okpd2_code = oom.okpd2_code
        JOIN okved2 ov ON ov.okved2_code = oom.okved2_code
        ORDER BY oom.okpd2_code, oom.okved2_code
        """
    )


@router.post("/okpd2-okved2")
def create_okpd2_okved2(p: Okpd2Okved2Create):
    try:
        return execute_returning(
            """
            INSERT INTO okpd2_okved2_map (okpd2_code, okved2_code, source_comment)
            VALUES (%s,%s,%s)
            RETURNING okpd2_code, okved2_code, source_comment
            """,
            (p.okpd2_code, p.okved2_code, p.source_comment),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/okpd2-okved2")
def delete_okpd2_okved2(okpd2_code: str, okved2_code: str):
    execute(
        "DELETE FROM okpd2_okved2_map WHERE okpd2_code=%s AND okved2_code=%s",
        (okpd2_code, okved2_code),
    )
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
        JOIN materials m ON m.material_id = mugm.material_id
        JOIN user_material_groups g ON g.id_possition = mugm.id_possition
        ORDER BY m.material_name, g.name_possition
        """
    )


@router.post("/material-user-group")
def create_material_user_group(p: MaterialUserGroupCreate):
    try:
        return execute_returning(
            """
            INSERT INTO material_user_group_map (material_id, id_possition, source_comment)
            VALUES (%s,%s,%s)
            RETURNING material_id, id_possition AS user_group_id, source_comment
            """,
            (p.material_id, p.user_group_id, p.source_comment),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/material-user-group")
def delete_material_user_group(material_id: str, user_group_id: str):
    execute(
        """
        DELETE FROM material_user_group_map
        WHERE material_id = %s
          AND id_possition = %s
        """,
        (material_id, user_group_id),
    )
    return {"status": "OK"}


@router.get("/user-group-supplier")
def get_user_group_supplier():
    return fetch_all(
        """
        SELECT
            ugsm.user_group_id,
            g.name_possition AS user_group_name,
            ugsm.inn_supply,
            s.name AS name_supply,
            ugsm.source_comment
        FROM user_group_supply_map ugsm
        JOIN user_material_groups g ON g.id_possition = ugsm.user_group_id
        JOIN suppliers s ON s.inn = ugsm.inn_supply
        ORDER BY g.name_possition, s.name, ugsm.inn_supply
        """
    )


@router.post("/user-group-supplier")
def create_user_group_supplier(p: UserGroupSupplierCreate):
    try:
        return execute_returning(
            """
            INSERT INTO user_group_supply_map (user_group_id, inn_supply, source_comment)
            VALUES (%s,%s,%s)
            RETURNING user_group_id, inn_supply, source_comment
            """,
            (p.user_group_id, p.supplier_inn, p.source_comment),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/user-group-supplier")
def delete_user_group_supplier(user_group_id: str, inn_supply: str):
    execute(
        """
        DELETE FROM user_group_supply_map
        WHERE user_group_id = %s
          AND inn_supply = %s
        """,
        (user_group_id, inn_supply),
    )
    return {"status": "OK"}
