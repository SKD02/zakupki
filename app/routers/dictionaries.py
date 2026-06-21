import re
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import fetch_all, execute, execute_returning, fetch_one, get_connection
from app.routers.upload import get_uploaded_file_path
from app.services.dictionary_excel_import import (get_dictionary_import_fields,import_dictionary_rows,read_dictionary_excel_rows)
from app.services.contracts import ensure_contract_schema, normalize_text, normalize_work_doc, ensure_work_doc_subject_row
from app.services.audit import log_action
from app.services.units import ensure_unit_names_storage, resolve_unit_code
from app.services.suppliers import ensure_supplier_id_schema, next_supplier_id, resolve_okved2_code

router = APIRouter()

MATERIAL_ID_PREFIX = "M"
MATERIAL_ID_DIGITS = 8

USER_GROUP_ID_PREFIX = "C"
USER_GROUP_ID_DIGITS = 3

UNIT_CODE_ID_PREFIX = "U"
UNIT_CODE_ID_DIGITS = 2

class UnitCreate(BaseModel):
    unit_code: Optional[str] = None
    unit_name: str
    description: Optional[str] = None
    force_create: bool = False


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

class DictionaryExcelImportRequest(BaseModel):
    upload_id: str
    sheet_name: str
    header_row: int = 1
    column_mapping: Dict[str, str]

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


def _audit(entity_type: str, entity_id=None, action: str = "CHANGE", details=None):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                log_action(cur, entity_type, entity_id, action, details)
                conn.commit()
    except Exception:
        pass

@router.get("/{dictionary_type}/import-fields")
def get_dictionary_import_fields_api(dictionary_type: str):
    try:
        return {
            "dictionary_type": dictionary_type,
            "fields": get_dictionary_import_fields(dictionary_type),
        }
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/{dictionary_type}/import-excel")
def import_dictionary_excel(dictionary_type: str, payload: DictionaryExcelImportRequest):
    try:
        fields = get_dictionary_import_fields(dictionary_type)
        file_path = get_uploaded_file_path(payload.upload_id)

        rows = read_dictionary_excel_rows(
            file_path=file_path,
            sheet_name=payload.sheet_name,
            header_row=payload.header_row,
            column_mapping=payload.column_mapping,
            fields=fields,
        )

        with get_connection() as conn:
            with conn.cursor() as cur:
                result = import_dictionary_rows(cur, dictionary_type, rows)
                log_action(cur, f"dictionary:{dictionary_type}", dictionary_type, "IMPORT_EXCEL", result)
                conn.commit()

        return result

    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/units")
def get_units():
    return fetch_all(
        """
        SELECT unit_code, unit_name, description
        FROM units
        ORDER BY unit_code
        """
    )


@router.post("/units")
def create_unit(payload: UnitCreate):
    unit_name = payload.unit_name.strip()
    description = _normalize_optional(payload.description)

    unit_code = _normalize_optional(payload.unit_code)

    if unit_code:
        unit_code = unit_code.strip().upper()
        same_unit_code = fetch_one(
            """
            SELECT unit_code, unit_name, description
            FROM units
            WHERE lower(btrim(unit_code)) = lower(btrim(%s))
            LIMIT 1
            """,
            (unit_code,),
        )

        if same_unit_code:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "UNIT_DUPLICATE_CODE",
                    "message": "Единица измерения с таким кодом уже есть в справочнике.",
                    "matches": [same_unit_code],
                },
            )

    same_unit_name = fetch_one(
        """
        SELECT unit_code, unit_name, description
        FROM units
        WHERE lower(btrim(unit_name)) = lower(btrim(%s))
        ORDER BY unit_code
        """,
        (unit_name, ),
    )

    if same_unit_name and not payload.force_create:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "UNIT_DUPLICATE_NAME",
                "message": "Единица измерения с таким наименованием уже есть в справочнике.",
                "matches": [same_unit_name],
                "requires_confirmation": True,
            },
        )

    if not unit_code:
        unit_code = _next_masked_id(
            "units",
            "unit_code",
            UNIT_CODE_ID_PREFIX,
            UNIT_CODE_ID_DIGITS,
        )

    try:
        created = execute_returning(
            """
            INSERT INTO units (unit_code, unit_name, description)
            VALUES (%s,%s,%s)
            RETURNING unit_code, unit_name, description
            """,
            (unit_code, unit_name, description),
        )
        _audit("units", created.get("unit_code"), "CREATE", created)
        return created
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
@router.delete("/units/{unit_code}")
def delete_unit(unit_code: str):
    linked_materials = fetch_all(
        """
        SELECT m.material_id, m.material_name, COALESCE(u.unit_name, m.unit) AS unit
        FROM materials m
        LEFT JOIN units u
            ON lower(btrim(u.unit_code)) = lower(btrim(m.unit))
            OR lower(btrim(u.unit_name)) = lower(btrim(m.unit))
        WHERE lower(btrim(m.unit)) = lower(btrim(%s))
           OR lower(btrim(u.unit_code)) = lower(btrim(%s))
           OR lower(btrim(u.unit_name)) = lower(btrim(%s))
        LIMIT 10
        """,
        (unit_code, unit_code, unit_code),
    )

    if linked_materials:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "UNIT_USED_BY_MATERIALS",
                "message": "Единицу измерения нельзя удалить: она используется в справочнике материалов.",
                "matches": linked_materials,
            },
        )

    try:
        execute(
            "DELETE FROM units WHERE unit_code = %s",
            (unit_code,),
        )
        _audit("units", unit_code, "DELETE", {"unit_code": unit_code})
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/materials")
def get_materials():
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
        ORDER BY m.material_name
        """
    )


@router.post("/materials")
def create_material(payload: MaterialCreate):
    material_name = payload.material_name.strip()
    unit = _normalize_optional(payload.unit.strip() if payload.unit else payload.unit)
    description = _normalize_optional(payload.description)

    if unit:
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_unit_names_storage(cur)
                unit_code = resolve_unit_code(cur, unit)
                conn.commit()

        if not unit_code:
            raise HTTPException(
                status_code=400,
                detail="Единица измерения отсутствует в справочнике. Сначала добавьте её во вкладке 'Единицы измерения'.",
            )
        unit = unit_code

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
        created = execute_returning(
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
        _audit("materials", created.get("material_id"), "CREATE", created)
        return created
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    
@router.delete("/materials/{material_id}")
def delete_material(material_id: str):
    try:
        execute(
            "DELETE FROM materials WHERE material_id = %s",
            (material_id,),
        )
        _audit("materials", material_id, "DELETE", {"material_id": material_id})
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
        _audit("okpd2", okpd2_code, "DELETE", {"okpd2_code": okpd2_code})
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
        _audit("okved2", okved2_code, "DELETE", {"okved2_code": okved2_code})
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
        created = execute_returning(
            """
            INSERT INTO user_material_groups (id_possition, name_possition, description)
            VALUES (%s,%s,%s)
            RETURNING id_possition, name_possition, description
            """,
            (group_id, name_possition, description),
        )
        _audit("user_material_groups", created.get("id_possition"), "CREATE", created)
        return created
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@router.delete("/user-groups/{id_possition}")
def delete_user_group(id_possition: str):
    try:
        execute(
            "DELETE FROM user_material_groups WHERE id_possition = %s",
            (id_possition,),
        )
        _audit("user_material_groups", id_possition, "DELETE", {"id_possition": id_possition})
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@router.get("/suppliers")
def get_suppliers():
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_supplier_id_schema(cur)
            conn.commit()

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
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_supplier_id_schema(cur)
                supplier_id = next_supplier_id(cur)

                cur.execute(
                    """
                    INSERT INTO suppliers (
                        supplier_id,
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
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        supplier_id,
                        payload.inn,
                        payload.name,
                        _normalize_optional(payload.short_name),
                        _normalize_optional(payload.registration_number),
                        _normalize_optional(payload.registration_date),
                        _normalize_optional(payload.address),
                        _normalize_optional(payload.management),
                        _normalize_optional(payload.management_position),
                        resolve_okved2_code(cur, payload.okved2_code, strict=True),
                        _normalize_optional(payload.organizational_legal_form),
                        _normalize_optional(payload.ownership_form),
                        _normalize_optional(payload.company_size),
                        _normalize_optional(payload.phone),
                        _normalize_optional(payload.email),
                        _normalize_optional(payload.website),
                        _normalize_optional(payload.tax_regime),
                    ),
                )
                supplier = cur.fetchone()

                if payload.report_year:
                    cur.execute(
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

                log_action(cur, "suppliers", supplier.get("supplier_id"), "CREATE", supplier)
                conn.commit()

        return supplier
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

@router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: str):
    try:
        execute(
            "DELETE FROM suppliers WHERE supplier_id = %s",
            (supplier_id,),
        )
        _audit("suppliers", supplier_id, "DELETE", {"supplier_id": supplier_id})
        return {"status": "OK"}
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    

@router.get("/work-doc-subjects")
def get_work_doc_subjects_dictionary():
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_contract_schema(cur)
            conn.commit()

    return fetch_all(
        """
        SELECT
            work_doc_code,
            work_doc_subject,
            description
        FROM work_document_subjects
        ORDER BY work_doc_code, work_doc_subject
        """
    )


class WorkDocSubjectCreate(BaseModel):
    work_doc_code: str
    work_doc_subject: str
    description: Optional[str] = None


@router.post("/work-doc-subjects")
def create_work_doc_subject_dictionary(payload: WorkDocSubjectCreate):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_contract_schema(cur)
                row = ensure_work_doc_subject_row(
                    cur,
                    payload.work_doc_code,
                    payload.work_doc_subject,
                    payload.description,
                )
                log_action(cur, "work_document_subjects", f"{row['work_doc_code']}|{row['work_doc_subject']}", "CREATE", row)
                conn.commit()

        return row

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete("/work-doc-subjects/{work_doc_code}/{work_doc_subject:path}")
def delete_work_doc_subject_dictionary_pair(work_doc_code: str, work_doc_subject: str):
    """Полностью удаляет пару шифр РД / предмет из справочника.

    Связанные строки договоров удаляются каскадно через FK contracts -> work_document_subjects.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_contract_schema(cur)
            cur.execute(
                """
                DELETE FROM work_document_subjects
                WHERE lower(btrim(work_doc_code)) = lower(btrim(%s))
                  AND lower(btrim(work_doc_subject)) = lower(btrim(%s))
                RETURNING work_doc_code, work_doc_subject
                """,
                (normalize_work_doc(work_doc_code), work_doc_subject),
            )
            deleted = cur.fetchall()
            for row in deleted:
                log_action(cur, "work_document_subjects", f"{row['work_doc_code']}|{row['work_doc_subject']}", "DELETE", row)
            conn.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail="Запись справочника Шифры РД не найдена")

    return {"status": "OK", "deleted_count": len(deleted), "deleted": deleted}


@router.delete("/work-doc-subjects/{work_doc_code}")
def delete_work_doc_subject_dictionary(work_doc_code: str):
    """Старый маршрут оставлен для совместимости: полностью удаляет все предметы по шифру РД."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_contract_schema(cur)
            cur.execute(
                """
                DELETE FROM work_document_subjects
                WHERE lower(btrim(work_doc_code)) = lower(btrim(%s))
                RETURNING work_doc_code, work_doc_subject
                """,
                (normalize_work_doc(work_doc_code),),
            )
            deleted = cur.fetchall()
            for row in deleted:
                log_action(cur, "work_document_subjects", f"{row['work_doc_code']}|{row['work_doc_subject']}", "DELETE", row)
            conn.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail="Записи справочника Шифры РД не найдены")

    return {"status": "OK", "deleted_count": len(deleted), "deleted": deleted}


