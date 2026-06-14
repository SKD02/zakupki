import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import fetch_all, execute, execute_returning

router = APIRouter()

MATERIAL_ID_PREFIX = "M"
MATERIAL_ID_DIGITS = 8

USER_GROUP_ID_PREFIX = "C"
USER_GROUP_ID_DIGITS = 3


class MaterialCreate(BaseModel):
    material_id: Optional[str] = None
    material_name: str
    unit: Optional[str] = None
    description: Optional[str] = None
    force_create: bool = False

class UserGroupCreate(BaseModel):
    id_possition: Optional[str] = None
    name_possition: str
    description: Optional[str] = None
    force_create: bool = False


class SupplierCreate(BaseModel):
    inn: str = Field(..., min_length=10, max_length=12)
    name: str
    short_name: Optional[str] = None
    registration_number: Optional[str] = None
    registration_date: Optional[str] = None
    address: Optional[str] = None
    management: Optional[str] = None
    management_position: Optional[str] = None
    okved2_code: Optional[str] = None
    organizational_legal_form: Optional[str] = None
    ownership_form: Optional[str] = None
    company_size: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    tax_regime: Optional[str] = None
    report_year: Optional[int] = None
    revenue_rub: Optional[float] = None
    net_profit_loss_rub: Optional[float] = None

def _normalize_search_text(value: str) -> str:
    value = value or ""
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value

def _next_masked_id(table: str, id_column: str, prefix: str, digits: int) -> str:
    rows = fetch_all(
        f"""
        SELECT {id_column} AS id_value
        FROM {table}
        WHERE {id_column} ~ %s
        ORDER BY {id_column} DESC
        LIMIT 1
        """,
        (f"^{prefix}[0-9]{{{digits}}}$",),
    )

    if not rows:
        return f"{prefix}{1:0{digits}d}"

    match = re.search(r"(\d+)$", rows[0]["id_value"] or "")
    next_no = int(match.group(1)) + 1 if match else 1
    return f"{prefix}{next_no:0{digits}d}"


def _normalize_optional(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


@router.get("/materials")
def get_materials():
    return fetch_all(
        """
        SELECT material_id, material_name, unit, description
        FROM materials
        ORDER BY material_name
        """
    )


@router.post("/materials")
def create_material(payload: MaterialCreate):
    material_name = payload.material_name.strip()
    unit = _normalize_optional(payload.unit)
    description = _normalize_optional(payload.description)

    same_name_same_unit = fetch_all(
        """
        SELECT material_id, material_name, unit, description
        FROM materials
        WHERE lower(btrim(material_name)) = lower(btrim(%s))
          AND COALESCE(lower(btrim(unit)), '') = COALESCE(lower(btrim(%s)), '')
        ORDER BY material_id
        """,
        (material_name, unit),
    )

    if same_name_same_unit:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MATERIAL_DUPLICATE_NAME_UNIT",
                "message": "Материал с таким наименованием и единицей измерения уже есть в справочнике.",
                "matches": same_name_same_unit,
            },
        )

    same_name_other_unit = fetch_all(
        """
        SELECT material_id, material_name, unit, description
        FROM materials
        WHERE lower(btrim(material_name)) = lower(btrim(%s))
          AND COALESCE(lower(btrim(unit)), '') <> COALESCE(lower(btrim(%s)), '')
        ORDER BY material_id
        """,
        (material_name, unit),
    )

    if same_name_other_unit and not payload.force_create:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MATERIAL_SAME_NAME_OTHER_UNIT",
                "message": "Материал с таким наименованием уже есть в справочнике, но с другой единицей измерения.",
                "matches": same_name_other_unit,
                "requires_confirmation": True,
            },
        )

    material_id = _normalize_optional(payload.material_id) or _next_masked_id(
        "materials",
        "material_id",
        MATERIAL_ID_PREFIX,
        MATERIAL_ID_DIGITS,
    )

    try:
        return execute_returning(
            """
            INSERT INTO materials (material_id, material_name, unit, description)
            VALUES (%s,%s,%s,%s)
            RETURNING material_id, material_name, unit, description
            """,
            (
                material_id,
                material_name,
                unit,
                description,
            ),
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    
@router.delete("/materials/{material_id}")
def delete_material(material_id: str):
    try:
        execute(
            "DELETE FROM materials WHERE material_id = %s",
            (material_id,),
        )
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
        
@router.get("/okpd2")
def get_okpd2():
    return fetch_all(
        """
        SELECT okpd2_code, name_okpd2
        FROM okpd2
        ORDER BY okpd2_code
        """
    )

@router.delete("/okpd2/{okpd2_code}")
def delete_okpd2(okpd2_code: str):
    try:
        execute(
            "DELETE FROM okpd2 WHERE okpd2_code = %s",
            (okpd2_code,),
        )
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    
@router.get("/okved2")
def get_okved2():
    return fetch_all(
        """
        SELECT okved2_code, name_okved2
        FROM okved2
        ORDER BY okved2_code
        """
    )

@router.delete("/okved2/{okved2_code}")
def delete_okved2(okved2_code: str):
    try:
        execute(
            "DELETE FROM okved2 WHERE okved2_code = %s",
            (okved2_code,),
        )
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@router.get("/user-groups")
def get_user_groups():
    return fetch_all(
        """
        SELECT id_possition, name_possition, description
        FROM user_material_groups
        ORDER BY name_possition
        """
    )


@router.post("/user-groups")
def create_user_group(payload: UserGroupCreate):
    name_possition = payload.name_possition.strip()
    description = _normalize_optional(payload.description)

    exact_matches = fetch_all(
        """
        SELECT id_possition, name_possition, description
        FROM user_material_groups
        WHERE lower(btrim(name_possition)) = lower(btrim(%s))
        ORDER BY id_possition
        """,
        (name_possition,),
    )

    if exact_matches:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "USER_GROUP_DUPLICATE_NAME",
                "message": "Группа с таким наименованием уже есть в справочнике.",
                "matches": exact_matches,
            },
        )

    normalized_input = _normalize_search_text(name_possition)
    input_words = [word for word in normalized_input.split(" ") if len(word) >= 4]

    similar_matches = []

    if input_words:
        rows = fetch_all(
            """
            SELECT id_possition, name_possition, description
            FROM user_material_groups
            ORDER BY id_possition
            """
        )

        for row in rows:
            normalized_existing = _normalize_search_text(row["name_possition"])

            matched_words = [
                word
                for word in input_words
                if word in normalized_existing
            ]

            existing_words = [
                word
                for word in normalized_existing.split(" ")
                if len(word) >= 4
            ]

            reverse_matched_words = [
                word
                for word in existing_words
                if word in normalized_input
            ]

            if matched_words or reverse_matched_words:
                similar_matches.append(
                    {
                        **row,
                        "match_reason": (
                            "Найдено частичное совпадение по словам: "
                            + ", ".join(sorted(set(matched_words + reverse_matched_words)))
                        ),
                    }
                )

    if similar_matches and not payload.force_create:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "USER_GROUP_SIMILAR_NAME",
                "message": "В справочнике уже есть похожие группы. Проверьте, точно ли нужно добавлять новую.",
                "matches": similar_matches[:10],
                "requires_confirmation": True,
            },
        )

    group_id = _normalize_optional(payload.id_possition) or _next_masked_id(
        "user_material_groups",
        "id_possition",
        USER_GROUP_ID_PREFIX,
        USER_GROUP_ID_DIGITS,
    )

    try:
        return execute_returning(
            """
            INSERT INTO user_material_groups (id_possition, name_possition, description)
            VALUES (%s,%s,%s)
            RETURNING id_possition, name_possition, description
            """,
            (group_id, name_possition, description),
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@router.delete("/user-groups/{id_possition}")
def delete_user_group(id_possition: str):
    try:
        execute(
            "DELETE FROM user_material_groups WHERE id_possition = %s",
            (id_possition,),
        )
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@router.get("/suppliers")
def get_suppliers():
    return fetch_all(
        """
        SELECT
            s.supplier_id,
            s.registration_number AS source_supplier_id,
            s.inn,
            s.name AS supplier_name,
            s.short_name,
            s.okved2_code AS primary_okved2_code,
            o.name_okved2 AS primary_okved2_name,
            s.phone AS phones,
            s.email AS emails,
            s.website,
            s.address AS legal_address,
            s.registration_date
        FROM suppliers s
        LEFT JOIN okved2 o ON o.okved2_code = s.okved2_code
        ORDER BY s.name, s.inn
        """
    )


@router.post("/suppliers")
def create_supplier(payload: SupplierCreate):
    try:
        supplier = execute_returning(
            """
            INSERT INTO suppliers (
                inn,
                name,
                short_name,
                registration_number,
                registration_date,
                address,
                management,
                management_position,
                okved2_code,
                organizational_legal_form,
                ownership_form,
                company_size,
                phone,
                email,
                website,
                tax_regime
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                payload.inn,
                payload.name,
                _normalize_optional(payload.short_name),
                _normalize_optional(payload.registration_number),
                _normalize_optional(payload.registration_date),
                _normalize_optional(payload.address),
                _normalize_optional(payload.management),
                _normalize_optional(payload.management_position),
                _normalize_optional(payload.okved2_code),
                _normalize_optional(payload.organizational_legal_form),
                _normalize_optional(payload.ownership_form),
                _normalize_optional(payload.company_size),
                _normalize_optional(payload.phone),
                _normalize_optional(payload.email),
                _normalize_optional(payload.website),
                _normalize_optional(payload.tax_regime),
            ),
        )

        if payload.report_year:
            execute_returning(
                """
                INSERT INTO supplier_financials (
                    supplier_id,
                    report_year,
                    revenue_rub,
                    net_profit_loss_rub
                )
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (supplier_id, report_year)
                DO UPDATE SET
                    revenue_rub = EXCLUDED.revenue_rub,
                    net_profit_loss_rub = EXCLUDED.net_profit_loss_rub
                RETURNING supplier_id, report_year
                """,
                (
                    supplier["supplier_id"],
                    payload.report_year,
                    payload.revenue_rub,
                    payload.net_profit_loss_rub,
                ),
            )

        return supplier
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: int):
    try:
        execute(
            "DELETE FROM suppliers WHERE supplier_id = %s",
            (supplier_id,),
        )
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))