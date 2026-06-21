from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_connection
from app.services.audit import log_action
from app.services.contracts import (
    contract_base_display,
    contract_display,
    ensure_contract_schema,
    ensure_work_doc_subject_row,
    next_contract_id,
    normalize_appendix,
    normalize_text,
    normalize_work_doc,
)

router = APIRouter()


class ContractWithWorkDocCreate(BaseModel):
    contract_no: str
    contract_date: Optional[str] = None
    # Приложение теперь хранится не в contracts, а в contract_work_doc_subjects.
    contract_appendix: Optional[str] = None
    work_doc_code: str
    work_doc_subject: Optional[str] = None
    work_doc_description: Optional[str] = None


class WorkDocSubjectCreate(BaseModel):
    work_doc_code: str
    work_doc_subject: str
    description: Optional[str] = None


@router.get("")
@router.get("/")
def get_contracts():
    """Реестр договоров: одна строка = один договор по номеру договора."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_contract_schema(cur)
            cur.execute(
                """
                WITH links AS (
                    SELECT DISTINCT
                        contract_id,
                        contract_appendix,
                        work_doc_code,
                        work_doc_subject,
                        contract_appendix || ' | ' || work_doc_code || ' - ' || work_doc_subject AS link_text
                    FROM contract_work_doc_subjects
                ),
                link_agg AS (
                    SELECT
                        contract_id,
                        string_agg(DISTINCT contract_appendix, ', ' ORDER BY contract_appendix) AS contract_appendices,
                        string_agg(DISTINCT work_doc_code, ', ' ORDER BY work_doc_code) AS work_doc_codes,
                        string_agg(DISTINCT work_doc_subject, ', ' ORDER BY work_doc_subject) AS work_doc_subjects,
                        string_agg(link_text, '; ' ORDER BY link_text) AS work_doc_links,
                        COUNT(*) AS links_count
                    FROM links
                    GROUP BY contract_id
                )
                SELECT
                    c.contract_id,
                    c.contract_no,
                    c.contract_date,
                    COALESCE(a.contract_appendices, '') AS contract_appendices,
                    COALESCE(a.work_doc_codes, '') AS work_doc_codes,
                    COALESCE(a.work_doc_subjects, '') AS work_doc_subjects,
                    COALESCE(a.work_doc_links, '') AS work_doc_links,
                    COALESCE(a.links_count, 0) AS links_count,
                    c.created_at,
                    c.updated_at
                FROM contracts c
                LEFT JOIN link_agg a ON a.contract_id = c.contract_id
                ORDER BY c.contract_id DESC
                """
            )
            rows = cur.fetchall()
            conn.commit()
            return rows


@router.get("/options")
def get_contract_options():
    """Опции для загрузки заявки: строки договора со всеми привязанными предметами."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_contract_schema(cur)
            cur.execute(
                """
                SELECT
                    c.contract_id,
                    c.contract_no,
                    c.contract_date,
                    l.contract_appendix,
                    l.work_doc_code,
                    l.work_doc_subject,
                    l.work_doc_subject AS contract_subject
                FROM contracts c
                JOIN contract_work_doc_subjects l
                  ON l.contract_id = c.contract_id
                JOIN work_document_subjects wds
                  ON wds.work_doc_code = l.work_doc_code
                 AND wds.work_doc_subject = l.work_doc_subject
                ORDER BY c.contract_no, l.contract_appendix, l.work_doc_code, l.work_doc_subject
                """
            )
            rows = cur.fetchall()
            conn.commit()

    return [
        {
            "value": row["contract_id"],
            "label": contract_display(row),
            **row,
        }
        for row in rows
    ]


@router.get("/work-doc-subjects")
def get_work_doc_subjects():
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_contract_schema(cur)
            cur.execute(
                """
                SELECT
                    work_doc_code,
                    work_doc_subject,
                    description,
                    created_at,
                    updated_at
                FROM work_document_subjects
                ORDER BY work_doc_code, work_doc_subject
                """
            )
            rows = cur.fetchall()
            conn.commit()

    return rows


@router.post("/work-doc-subjects")
def create_work_doc_subject(payload: WorkDocSubjectCreate):
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
                log_action(
                    cur,
                    "work_document_subjects",
                    f"{row['work_doc_code']}|{row['work_doc_subject']}",
                    "CREATE",
                    row,
                )
                conn.commit()
        return row
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("")
@router.post("/")
def create_contract(payload: ContractWithWorkDocCreate):
    return create_contract_with_work_doc(payload)


@router.post("/with-work-doc")
def create_contract_with_work_doc(payload: ContractWithWorkDocCreate):
    """
    Создаёт/находит один договор по номеру договора и добавляет связи:
    приложение + выбранный шифр РД + все предметы этого шифра из справочника.
    """
    contract_no = normalize_text(payload.contract_no)
    contract_date = normalize_text(payload.contract_date)
    contract_appendix = normalize_appendix(payload.contract_appendix)
    work_doc_code = normalize_work_doc(payload.work_doc_code)

    if not contract_no:
        raise HTTPException(status_code=400, detail="Номер договора обязателен")
    if not work_doc_code:
        raise HTTPException(status_code=400, detail="Шифр РД обязателен")

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                ensure_contract_schema(cur)

                cur.execute(
                    """
                    SELECT work_doc_code, work_doc_subject
                    FROM work_document_subjects
                    WHERE lower(btrim(work_doc_code)) = lower(btrim(%s))
                    ORDER BY work_doc_subject
                    """,
                    (work_doc_code,),
                )
                subjects = cur.fetchall()

                if not subjects:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "WORK_DOC_SUBJECTS_EMPTY",
                            "message": "Для выбранного шифра РД нет предметов в справочнике. Сначала добавьте предметы в справочник “Шифры РД”.",
                            "redirect_url": "/dict/work-doc-subjects",
                        },
                    )

                cur.execute(
                    """
                    SELECT
                        contract_id,
                        contract_no,
                        contract_date
                    FROM contracts
                    WHERE lower(btrim(contract_no)) = lower(btrim(%s))
                    LIMIT 1
                    """,
                    (contract_no,),
                )
                contract = cur.fetchone()
                created_contract = False

                if not contract:
                    contract_id = next_contract_id(cur)
                    cur.execute(
                        """
                        INSERT INTO contracts (
                            contract_id,
                            contract_no,
                            contract_date,
                            contract_appendix,
                            updated_at
                        )
                        VALUES (%s,%s,%s,NULL,now())
                        RETURNING
                            contract_id,
                            contract_no,
                            contract_date
                        """,
                        (contract_id, contract_no, contract_date),
                    )
                    contract = cur.fetchone()
                    created_contract = True
                elif contract_date and not contract.get("contract_date"):
                    cur.execute(
                        """
                        UPDATE contracts
                        SET contract_date = %s::date,
                            updated_at = now()
                        WHERE contract_id = %s
                        RETURNING contract_id, contract_no, contract_date
                        """,
                        (contract_date, contract["contract_id"]),
                    )
                    contract = cur.fetchone()

                created_links = []
                existing_links = []

                for subject in subjects:
                    cur.execute(
                        """
                        INSERT INTO contract_work_doc_subjects (
                            contract_id,
                            contract_appendix,
                            work_doc_code,
                            work_doc_subject,
                            updated_at
                        )
                        VALUES (%s,%s,%s,%s,now())
                        ON CONFLICT (contract_id, contract_appendix, work_doc_code, work_doc_subject)
                        DO UPDATE SET
                            updated_at = now()
                        RETURNING
                            contract_id,
                            contract_appendix,
                            work_doc_code,
                            work_doc_subject,
                            (xmax = 0) AS inserted
                        """,
                        (
                            contract["contract_id"],
                            contract_appendix,
                            subject["work_doc_code"],
                            subject["work_doc_subject"],
                        ),
                    )
                    link = cur.fetchone()
                    if link.get("inserted"):
                        created_links.append(link)
                    else:
                        existing_links.append(link)

                log_action(
                    cur,
                    "contracts",
                    contract["contract_id"],
                    "CREATE" if created_contract else "UPDATE_LINKS",
                    {
                        "contract": dict(contract),
                        "contract_appendix": contract_appendix,
                        "work_doc_code": work_doc_code,
                        "created_links_count": len(created_links),
                        "existing_links_count": len(existing_links),
                    },
                )
                conn.commit()

        return {
            "status": "OK" if created_contract or created_links else "EXISTS",
            "contract_id": contract["contract_id"],
            "label": contract_base_display(contract),
            "contract_appendix": contract_appendix,
            "created_contract": created_contract,
            "created_count": len(created_links),
            "existing_count": len(existing_links),
            "subjects_count": len(subjects),
            "created": created_links,
            "existing": existing_links,
            **contract,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete("/{contract_id}")
def delete_contract(contract_id: str):
    """Полностью удаляет договор и все его связи с РД/предметами."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            ensure_contract_schema(cur)
            cur.execute(
                """
                DELETE FROM contracts
                WHERE contract_id = %s
                RETURNING contract_id, contract_no, contract_date
                """,
                (contract_id,),
            )
            deleted = cur.fetchone()

            if not deleted:
                conn.commit()
                raise HTTPException(status_code=404, detail="Договор не найден")

            log_action(cur, "contracts", contract_id, "DELETE", deleted)
            conn.commit()

    return {
        "status": "OK",
        "contract_id": contract_id,
        "deleted_count": 1,
        "deleted_contract_ids": [contract_id],
    }
