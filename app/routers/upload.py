import os
import json
import shutil
from datetime import date, datetime
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.database import get_connection
from app.services.excel_parser import (
    get_excel_sheets,
    get_sheet_preview,
    read_application_excel,
    read_application_excel_with_mapping,
    normalize,
    parse_supply_period,
)

router = APIRouter()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ExcelPreviewRequest(BaseModel):
    upload_id: str
    sheet_name: str
    header_row: int = 1


class ApplicationConfiguredUploadRequest(BaseModel):
    upload_id: str
    sheet_name: str
    header_row: int
    column_mapping: Dict[str, str]
    approved_source_row_nos: Optional[List[int]] = None


class ManualApplicationItem(BaseModel):
    material_name: str
    unit: Optional[str] = None
    quantity: Any
    work_doc_code: Optional[str] = None
    supply_period: Optional[Any] = None


class ManualApplicationUploadRequest(BaseModel):
    items: List[ManualApplicationItem]


def get_uploaded_file_path(upload_id: str):
    file_path = os.path.join(UPLOAD_DIR, upload_id)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="Загруженный файл не найден. Загрузите Excel повторно."
        )

    return file_path


def save_upload_file(file: UploadFile):
    if not file.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="Необходимо загрузить Excel-файл")

    safe_filename = file.filename.replace("\\", "_").replace("/", "_")
    upload_id = f"{int(datetime.now().timestamp())}_{safe_filename}"
    file_path = os.path.join(UPLOAD_DIR, upload_id)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return upload_id, file_path


def clean_manual_value(value):
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def parse_manual_quantity(value):
    if value is None:
        return 0

    text = str(value).strip().replace(",", ".")

    if not text:
        return 0

    try:
        return float(text)
    except Exception:
        return 0


def build_manual_items(items: List[ManualApplicationItem]):
    result = []

    for index, item in enumerate(items, start=1):
        material_name = clean_manual_value(item.material_name)

        if not material_name:
            continue

        supply_start_date, supply_end_date = parse_supply_period(item.supply_period)

        raw_payload = {
            "material_name": item.material_name,
            "unit": item.unit,
            "quantity": item.quantity,
            "work_doc_code": item.work_doc_code,
            "supply_period": item.supply_period,
            "source": "manual_input",
        }

        result.append({
            "source_row_no": index,
            "material_name": material_name,
            "unit": clean_manual_value(item.unit),
            "quantity": parse_manual_quantity(item.quantity),
            "work_doc_code": clean_manual_value(item.work_doc_code),
            "supply_start_date": supply_start_date,
            "supply_end_date": supply_end_date,
            "raw_payload": raw_payload,
        })

    return result


@router.post("/excel/init")
def init_excel_upload(file: UploadFile = File(...)):
    upload_id, file_path = save_upload_file(file)

    try:
        sheets_info = get_excel_sheets(file_path)
        return {
            "status": "OK",
            "upload_id": upload_id,
            "original_filename": file.filename,
            "sheets": sheets_info["sheets"],
        }
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка чтения Excel-файла: {str(error)}"
        )


@router.post("/excel/preview")
def preview_excel_sheet(payload: ExcelPreviewRequest):
    file_path = get_uploaded_file_path(payload.upload_id)

    result = get_sheet_preview(
        file_path=file_path,
        sheet_name=payload.sheet_name,
        header_row=payload.header_row,
        preview_rows=15,
    )

    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result)

    return result


def create_application_from_items(
    items: list,
    source_file_name: str,
    source_file_path: str,
    raw_payload: dict,
):
    if not items:
        raise HTTPException(status_code=400, detail="На выбранном листе не найдено ни одной позиции")

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT material_id, material_name, unit FROM materials")

                material_map = {
                    f"{normalize(m['material_name'])}|{normalize(m['unit'])}": m
                    for m in cur.fetchall()
                }

                missing = []
                invalid_rows = []

                for item in items:
                    key = f"{normalize(item['material_name'])}|{normalize(item['unit'])}"
                    found = material_map.get(key)

                    if not found:
                        missing.append({
                            "row": item["source_row_no"],
                            "material_name": item["material_name"],
                            "unit": item["unit"],
                        })
                    else:
                        item["material_id"] = found["material_id"]

                    if not item.get("quantity") or float(item["quantity"]) <= 0:
                        invalid_rows.append({
                            "row": item["source_row_no"],
                            "material_name": item["material_name"],
                            "unit": item["unit"],
                            "error": "Количество должно быть больше 0",
                        })

                    if item.get("supply_start_date") and item.get("supply_end_date"):
                        if item["supply_start_date"] > item["supply_end_date"]:
                            invalid_rows.append({
                                "row": item["source_row_no"],
                                "material_name": item["material_name"],
                                "unit": item["unit"],
                                "error": "Дата начала поставки больше даты окончания поставки",
                            })

                if missing:
                    return {
                        "status": "MATERIALS_NOT_FOUND",
                        "message": "В справочнике отсутствуют материалы или единицы измерения",
                        "redirect_url": "/dictionaries",
                        "missing": missing,
                    }

                if invalid_rows:
                    return {
                        "status": "VALIDATION_ERROR",
                        "message": "В строках заявки есть ошибки",
                        "errors": invalid_rows,
                    }

                application_no = f"AUTO-{date.today().isoformat()}-{source_file_name}"

                cur.execute(
                    """
                    INSERT INTO purchase_applications (
                        application_no,
                        application_date,
                        construction_object,
                        source_file_name,
                        source_file_path,
                        raw_payload
                    )
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                    RETURNING application_id
                    """,
                    (
                        application_no,
                        date.today(),
                        None,
                        source_file_name,
                        source_file_path,
                        json.dumps(raw_payload, ensure_ascii=False, default=str),
                    ),
                )

                application_id = cur.fetchone()["application_id"]

                for item in items:
                    cur.execute(
                        """
                        INSERT INTO purchase_application_items (
                            application_id,
                            source_row_no,
                            material_id,
                            material_name,
                            unit,
                            quantity,
                            work_doc_code,
                            supply_start_date,
                            supply_end_date,
                            processing_status,
                            raw_payload
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                        """,
                        (
                            application_id,
                            item["source_row_no"],
                            item["material_id"],
                            item["material_name"],
                            item["unit"],
                            item["quantity"],
                            item["work_doc_code"],
                            item["supply_start_date"],
                            item["supply_end_date"],
                            "NEW",
                            json.dumps(item["raw_payload"], ensure_ascii=False, default=str),
                        ),
                    )

        return {
            "status": "OK",
            "message": "Заявка успешно загружена",
            "application_id": application_id,
            "items_count": len(items),
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки заявки: {str(error)}")
    finally:
        conn.close()


@router.post("/application-configured")
def upload_application_configured(payload: ApplicationConfiguredUploadRequest):
    file_path = get_uploaded_file_path(payload.upload_id)

    parsed = read_application_excel_with_mapping(
        file_path=file_path,
        sheet_name=payload.sheet_name,
        header_row=payload.header_row,
        column_mapping=payload.column_mapping,
    )

    if not parsed["ok"]:
        raise HTTPException(status_code=400, detail=parsed)

    items = parsed["items"]
    skipped_items = []

    if payload.approved_source_row_nos is not None:
        approved_set = set(payload.approved_source_row_nos)

        skipped_items = [
            item
            for item in items
            if item.get("source_row_no") not in approved_set
        ]

        items = [
            item
            for item in items
            if item.get("source_row_no") in approved_set
        ]

    if not items:
        return {
            "status": "NO_APPROVED_ITEMS",
            "message": "Не выбрано ни одной согласованной позиции для загрузки.",
            "skipped_count": len(skipped_items),
            "skipped": [
                {
                    "row": item.get("source_row_no"),
                    "material_name": item.get("material_name"),
                    "unit": item.get("unit"),
                    "quantity": item.get("quantity"),
                }
                for item in skipped_items
            ],
        }

    return create_application_from_items(
        items=items,
        source_file_name=payload.upload_id,
        source_file_path=file_path,
        raw_payload={
            "sheet_name": parsed["sheet_name"],
            "header_row": parsed["header_row"],
            "column_mapping": parsed["column_mapping"],
            "source": "excel_configured_upload",
            "approved_source_row_nos": payload.approved_source_row_nos,
            "skipped_items": skipped_items,
        },
    )

@router.post("/application-manual")
def upload_application_manual(payload: ManualApplicationUploadRequest):
    items = build_manual_items(payload.items)

    return create_application_from_items(
        items=items,
        source_file_name=f"manual-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        source_file_path="manual_input",
        raw_payload={
            "source": "manual_input",
            "items": [item.dict() for item in payload.items],
        },
    )


@router.post("/application")
def upload_application(file: UploadFile = File(...)):
    """
    Старый endpoint оставлен для совместимости.
    Новый интерфейс использует /excel/init, /excel/preview и /application-configured.
    """
    upload_id, file_path = save_upload_file(file)

    parsed = read_application_excel(file_path)

    if not parsed["ok"]:
        raise HTTPException(status_code=400, detail=parsed)

    return create_application_from_items(
        items=parsed["items"],
        source_file_name=upload_id,
        source_file_path=file_path,
        raw_payload={
            "sheet_name": parsed.get("sheet_name"),
            "source": "excel_upload_legacy",
        },
    )