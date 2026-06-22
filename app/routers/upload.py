# import os
# import json
# import shutil
# from datetime import date, datetime
# from typing import Dict, List, Optional, Any

# from fastapi import APIRouter, UploadFile, File, HTTPException
# from pydantic import BaseModel

# from app.database import get_connection
# from app.services.excel_parser import (
#     get_excel_sheets,
#     get_sheet_preview,
#     read_application_excel,
#     read_application_excel_with_mapping,
#     normalize,
#     parse_supply_period,
# )

# from app.services.contracts import (
#     ensure_application_subject_schema,
#     ensure_contract_schema,
#     normalize_key,
#     normalize_text,
#     normalize_work_doc,
#     validate_work_doc_rows,
# )
# from app.services.units import ensure_unit_names_storage
# router = APIRouter()
# UPLOAD_DIR = "uploads"
# os.makedirs(UPLOAD_DIR, exist_ok=True)


# class ExcelPreviewRequest(BaseModel):
#     upload_id: str
#     sheet_name: str
#     header_row: int = 1


# class ApplicationConfiguredUploadRequest(BaseModel):
#     upload_id: str
#     sheet_name: str
#     header_row: int
#     column_mapping: Dict[str, str]
#     approved_source_row_nos: Optional[List[int]] = None
#     contract_id: Optional[str] = None
#     validate_only: bool = False
#     # Старые поля оставлены для совместимости. В новой логике шифр РД и предмет
#     # берутся из строк Excel/ручного ввода, а не из верхних фильтров.
#     work_doc_code: Optional[str] = None
#     work_doc_subject: Optional[str] = None


# class ManualApplicationItem(BaseModel):
#     material_name: str
#     unit: Optional[str] = None
#     quantity: Any
#     work_doc_code: Optional[str] = None
#     work_doc_subject: Optional[str] = None
#     supply_period: Optional[Any] = None


# class ManualApplicationUploadRequest(BaseModel):
#     items: List[ManualApplicationItem]
#     contract_id: Optional[str] = None
#     validate_only: bool = False
#     work_doc_code: Optional[str] = None
#     work_doc_subject: Optional[str] = None


# def get_uploaded_file_path(upload_id: str):
#     file_path = os.path.join(UPLOAD_DIR, upload_id)

#     if not os.path.exists(file_path):
#         raise HTTPException(
#             status_code=404,
#             detail="Загруженный файл не найден. Загрузите Excel повторно."
#         )

#     return file_path


# def save_upload_file(file: UploadFile):
#     if not file.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
#         raise HTTPException(status_code=400, detail="Необходимо загрузить Excel-файл")

#     safe_filename = file.filename.replace("\\", "_").replace("/", "_")
#     upload_id = f"{int(datetime.now().timestamp())}_{safe_filename}"
#     file_path = os.path.join(UPLOAD_DIR, upload_id)

#     with open(file_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)

#     return upload_id, file_path


# def clean_manual_value(value):
#     if value is None:
#         return None

#     text = str(value).strip()
#     return text or None


# def parse_manual_quantity(value):
#     if value is None:
#         return 0

#     text = str(value).strip().replace(",", ".")

#     if not text:
#         return 0

#     try:
#         return float(text)
#     except Exception:
#         return 0


# def build_manual_items(items: List[ManualApplicationItem]):
#     result = []

#     for index, item in enumerate(items, start=1):
#         material_name = clean_manual_value(item.material_name)

#         if not material_name:
#             continue

#         supply_start_date, supply_end_date = parse_supply_period(item.supply_period)

#         raw_payload = {
#             "material_name": item.material_name,
#             "unit": item.unit,
#             "quantity": item.quantity,
#             "work_doc_code": item.work_doc_code,
#             "work_doc_subject": item.work_doc_subject,
#             "supply_period": item.supply_period,
#             "source": "manual_input",
#         }

#         result.append({
#             "source_row_no": index,
#             "material_name": material_name,
#             "unit": clean_manual_value(item.unit),
#             "quantity": parse_manual_quantity(item.quantity),
#             "work_doc_code": clean_manual_value(item.work_doc_code),
#             "work_doc_subject": clean_manual_value(item.work_doc_subject),
#             "supply_start_date": supply_start_date,
#             "supply_end_date": supply_end_date,
#             "raw_payload": raw_payload,
#         })

#     return result


# def resolve_contract_for_upload(cur, contract_id: str):
#     """
#     В новой модели contract_id — это один договор.
#     РД/предметы берутся из contract_work_doc_subjects.
#     """
#     cur.execute(
#         """
#         SELECT
#             c.contract_id,
#             c.contract_no,
#             c.contract_date,
#             NULL::text AS contract_appendix
#         FROM contracts c
#         WHERE c.contract_id = %s
#         LIMIT 1
#         """,
#         (contract_id,),
#     )
#     selected = cur.fetchone()

#     if not selected:
#         return None

#     cur.execute(
#         """
#         SELECT
#             l.contract_id,
#             c.contract_no,
#             c.contract_date,
#             l.contract_appendix,
#             l.work_doc_code,
#             l.work_doc_subject,
#             l.work_doc_subject AS contract_subject
#         FROM contract_work_doc_subjects l
#         JOIN contracts c ON c.contract_id = l.contract_id
#         JOIN work_document_subjects wds
#           ON wds.work_doc_code = l.work_doc_code
#          AND wds.work_doc_subject = l.work_doc_subject
#         WHERE l.contract_id = %s
#         ORDER BY l.work_doc_code, l.work_doc_subject
#         """,
#         (selected["contract_id"],),
#     )
#     rows = cur.fetchall()

#     selected["contract_rows"] = rows
#     selected["contract_subject"] = ", ".join(sorted({row["work_doc_subject"] for row in rows if row.get("work_doc_subject")}))
#     return selected


# def validate_contract_work_docs(contract, items):
#     rows = contract.get("contract_rows") or []
#     allowed_pairs = {
#         (normalize_work_doc(row.get("work_doc_code")), normalize_key(row.get("work_doc_subject")))
#         for row in rows
#     }

#     missing = []

#     for item in items:
#         pair = (
#             normalize_work_doc(item.get("work_doc_code")),
#             normalize_key(item.get("work_doc_subject")),
#         )

#         if pair not in allowed_pairs:
#             missing.append({
#                 "row": item.get("source_row_no"),
#                 "material_name": item.get("material_name"),
#                 "unit": item.get("unit"),
#                 "quantity": item.get("quantity"),
#                 "work_doc_code": item.get("work_doc_code"),
#                 "work_doc_subject": item.get("work_doc_subject"),
#                 "contract_no": contract.get("contract_no"),
#                 "error": "В выбранном договоре нет связи с этой парой шифр РД / предмет по РД",
#             })

#     return missing


# def resolve_item_units(cur, items):
#     ensure_unit_names_storage(cur)
#     cur.execute("SELECT unit_code, unit_name FROM units")
#     unit_map = {}
#     unit_aliases_by_name = {}

#     for row in cur.fetchall():
#         code = row.get("unit_code")
#         name = row.get("unit_name")
#         canonical = code or name
#         display_name = name or code
#         aliases = set()

#         if code:
#             unit_map[normalize_key(code)] = {"code": canonical, "name": display_name}
#             aliases.add(code)
#         if name:
#             unit_map[normalize_key(name)] = {"code": canonical, "name": display_name}
#             aliases.add(name)

#         if canonical:
#             unit_aliases_by_name.setdefault(canonical, set()).update(aliases)

#     missing = []

#     for item in items:
#         unit_value = item.get("unit")
#         unit_key = normalize_key(unit_value)

#         if not unit_key or unit_key not in unit_map:
#             missing.append({
#                 "row": item.get("source_row_no"),
#                 "material_name": item.get("material_name"),
#                 "unit": unit_value,
#                 "quantity": item.get("quantity"),
#                 "work_doc_code": item.get("work_doc_code"),
#                 "work_doc_subject": item.get("work_doc_subject"),
#                 "error": "Единица измерения не найдена в справочнике",
#             })
#             continue

#         resolved_unit = unit_map[unit_key]
#         item["raw_payload"] = {
#             **(item.get("raw_payload") or {}),
#             "source_unit": unit_value,
#             "resolved_unit": resolved_unit["name"],
#             "resolved_unit_code": resolved_unit["code"],
#         }
#         item["unit"] = resolved_unit["code"]

#     return missing


# def build_unit_alias_lookup(cur):
#     ensure_unit_names_storage(cur)
#     cur.execute("SELECT unit_code, unit_name FROM units")
#     unit_to_canonical = {}
#     canonical_to_aliases = {}

#     for row in cur.fetchall():
#         code = row.get("unit_code")
#         name = row.get("unit_name")
#         canonical = code or name
#         aliases = {value for value in [code, name] if value}

#         if not canonical:
#             continue

#         canonical_to_aliases.setdefault(normalize_key(canonical), set()).update(aliases | {canonical})

#         for alias in aliases | {canonical}:
#             unit_to_canonical[normalize_key(alias)] = canonical

#     return unit_to_canonical, canonical_to_aliases


# def build_material_map(cur):
#     """Материалы могли быть сохранены как с кодами единиц (U19), так и с названиями (шт).
#     Для проверки строим ключи по обоим вариантам, чтобы не получать ложную ошибку.
#     """
#     unit_to_canonical, canonical_to_aliases = build_unit_alias_lookup(cur)
#     cur.execute("SELECT material_id, material_name, unit FROM materials")

#     material_map = {}

#     for material in cur.fetchall():
#         material_name_key = normalize(material["material_name"])
#         raw_unit = material.get("unit")
#         raw_unit_key = normalize_key(raw_unit)
#         canonical = unit_to_canonical.get(raw_unit_key, raw_unit)
#         alias_values = {raw_unit, canonical}

#         if canonical:
#             alias_values.update(canonical_to_aliases.get(normalize_key(canonical), set()))

#         for alias in alias_values:
#             if alias is None:
#                 continue
#             key = f"{material_name_key}|{normalize(alias)}"
#             material_map[key] = material

#     return material_map


# @router.post("/excel/init")
# def init_excel_upload(file: UploadFile = File(...)):
#     upload_id, file_path = save_upload_file(file)

#     try:
#         sheets_info = get_excel_sheets(file_path)
#         return {
#             "status": "OK",
#             "upload_id": upload_id,
#             "original_filename": file.filename,
#             "sheets": sheets_info["sheets"],
#         }
#     except Exception as error:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Ошибка чтения Excel-файла: {str(error)}"
#         )


# @router.post("/excel/preview")
# def preview_excel_sheet(payload: ExcelPreviewRequest):
#     file_path = get_uploaded_file_path(payload.upload_id)

#     result = get_sheet_preview(
#         file_path=file_path,
#         sheet_name=payload.sheet_name,
#         header_row=payload.header_row,
#         preview_rows=1000,
#     )

#     if not result["ok"]:
#         raise HTTPException(status_code=400, detail=result)

#     return result


# def create_application_from_items(
#     items: list,
#     source_file_name: str,
#     source_file_path: str,
#     raw_payload: dict,
#     contract_id: Optional[str] = None,
#     work_doc_subject: Optional[str] = None,
#     validate_only: bool = False,
# ):
#     if not items:
#         raise HTTPException(status_code=400, detail="На выбранном листе не найдено ни одной позиции")

#     conn = get_connection()

#     try:
#         with conn:
#             with conn.cursor() as cur:
#                 ensure_contract_schema(cur)
#                 ensure_application_subject_schema(cur)

#                 if not contract_id:
#                     return {
#                         "status": "CONTRACT_NOT_SELECTED",
#                         "message": "Перед загрузкой заявки выберите договор из реестра договоров.",
#                         "redirect_url": "/contracts",
#                     }

#                 contract = resolve_contract_for_upload(cur, contract_id=contract_id)

#                 if not contract:
#                     return {
#                         "status": "CONTRACT_NOT_FOUND",
#                         "message": "Выбранный договор не найден в реестре договоров.",
#                         "redirect_url": "/contracts",
#                     }

#                 selected_subject = normalize_text(work_doc_subject)

#                 if not selected_subject:
#                     return {
#                         "status": "CONTRACT_SUBJECT_NOT_SELECTED",
#                         "message": "Перед загрузкой заявки выберите предмет, привязанный к договору.",
#                         "redirect_url": "/contracts",
#                     }

#                 for item in items:
#                     item["work_doc_subject"] = selected_subject
#                     item["raw_payload"] = {
#                         **(item.get("raw_payload") or {}),
#                         "selected_work_doc_subject": selected_subject,
#                     }

#                 missing_work_docs = validate_work_doc_rows(cur, items)

#                 if missing_work_docs:
#                     return {
#                         "status": "WORK_DOCS_NOT_FOUND",
#                         "message": "В заявке есть строки с шифрами РД/предметами, которых нет в справочнике.",
#                         "redirect_url": "/dict/work-doc-subjects",
#                         "missing_work_docs": missing_work_docs,
#                     }

#                 missing_contract_links = validate_contract_work_docs(contract, items)

#                 if missing_contract_links:
#                     return {
#                         "status": "CONTRACT_WORK_DOCS_NOT_LINKED",
#                         "message": "В выбранном договоре нет связей с некоторыми РД/предметами из заявки.",
#                         "redirect_url": "/contracts",
#                         "missing_contract_work_docs": missing_contract_links,
#                     }

#                 missing_units = resolve_item_units(cur, items)

#                 if missing_units:
#                     return {
#                         "status": "UNITS_NOT_FOUND",
#                         "message": "В заявке есть единицы измерения, которых нет в справочнике.",
#                         "redirect_url": "/dict/units",
#                         "missing_units": missing_units,
#                     }

#                 material_map = build_material_map(cur)

#                 missing = []
#                 invalid_rows = []

#                 for item in items:
#                     key = f"{normalize(item['material_name'])}|{normalize(item['unit'])}"
#                     found = material_map.get(key)

#                     if not found:
#                         missing.append({
#                             "row": item["source_row_no"],
#                             "material_name": item["material_name"],
#                             "unit": item["unit"],
#                             "work_doc_code": item.get("work_doc_code"),
#                             "work_doc_subject": item.get("work_doc_subject"),
#                         })
#                     else:
#                         item["material_id"] = found["material_id"]

#                     if not item.get("quantity") or float(item["quantity"]) <= 0:
#                         invalid_rows.append({
#                             "row": item["source_row_no"],
#                             "material_name": item["material_name"],
#                             "unit": item["unit"],
#                             "error": "Количество должно быть больше 0",
#                         })

#                     if item.get("supply_start_date") and item.get("supply_end_date"):
#                         if item["supply_start_date"] > item["supply_end_date"]:
#                             invalid_rows.append({
#                                 "row": item["source_row_no"],
#                                 "material_name": item["material_name"],
#                                 "unit": item["unit"],
#                                 "error": "Дата начала поставки больше даты окончания поставки",
#                             })

#                 if missing:
#                     return {
#                         "status": "MATERIALS_NOT_FOUND",
#                         "message": "В справочнике отсутствуют материалы с указанными единицами измерения.",
#                         "redirect_url": "/dict/materials",
#                         "missing": missing,
#                     }

#                 if invalid_rows:
#                     return {
#                         "status": "VALIDATION_ERROR",
#                         "message": "В строках заявки есть ошибки",
#                         "errors": invalid_rows,
#                     }

#                 if validate_only:
#                     return {
#                         "status": "VALIDATION_OK",
#                         "message": "Проверка успешно пройдена. Можно загружать заявку в базу.",
#                         "items_count": len(items),
#                         "contract_id": contract["contract_id"],
#                         "contract_no": contract["contract_no"],
#                         "work_doc_subject": selected_subject,
#                     }

#                 distinct_subjects = []
#                 distinct_pairs = []
#                 seen_subjects = set()
#                 seen_pairs = set()

#                 for item in items:
#                     subject = normalize_text(item.get("work_doc_subject"))
#                     pair = (
#                         normalize_work_doc(item.get("work_doc_code")),
#                         normalize_key(item.get("work_doc_subject")),
#                     )

#                     if subject and normalize_key(subject) not in seen_subjects:
#                         distinct_subjects.append(subject)
#                         seen_subjects.add(normalize_key(subject))

#                     if pair not in seen_pairs:
#                         distinct_pairs.append({
#                             "work_doc_code": item.get("work_doc_code"),
#                             "work_doc_subject": item.get("work_doc_subject"),
#                         })
#                         seen_pairs.add(pair)

#                 application_no = f"AUTO-{date.today().isoformat()}-{source_file_name}"
#                 contract_subject = ", ".join(distinct_subjects) if distinct_subjects else contract.get("contract_subject")

#                 cur.execute(
#                     """
#                     INSERT INTO purchase_applications (
#                         application_no,
#                         application_date,
#                         construction_object,
#                         contract_id,
#                         contract_no,
#                         contract_date,
#                         contract_appendix,
#                         contract_subject,
#                         source_file_name,
#                         source_file_path,
#                         raw_payload
#                     )
#                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
#                     RETURNING application_id
#                     """,
#                     (
#                         application_no,
#                         date.today(),
#                         None,
#                         contract["contract_id"],
#                         contract["contract_no"],
#                         contract["contract_date"],
#                         contract["contract_appendix"],
#                         contract_subject,
#                         source_file_name,
#                         source_file_path,
#                         json.dumps(
#                             {
#                                 **raw_payload,
#                                 "contract_id": contract["contract_id"],
#                                 "contract_no": contract["contract_no"],
#                                 "contract_date": contract["contract_date"],
#                                 "contract_appendix": contract["contract_appendix"],
#                                 "contract_subject": contract_subject,
#                                 "work_doc_pairs": distinct_pairs,
#                             },
#                             ensure_ascii=False,
#                             default=str,
#                         ),
#                     ),
#                 )

#                 application_id = cur.fetchone()["application_id"]

#                 for item in items:
#                     cur.execute(
#                         """
#                         INSERT INTO purchase_application_items (
#                             application_id,
#                             source_row_no,
#                             material_id,
#                             material_name,
#                             unit,
#                             quantity,
#                             work_doc_code,
#                             work_doc_subject,
#                             supply_start_date,
#                             supply_end_date,
#                             processing_status,
#                             raw_payload
#                         )
#                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
#                         """,
#                         (
#                             application_id,
#                             item["source_row_no"],
#                             item["material_id"],
#                             item["material_name"],
#                             item["unit"],
#                             item["quantity"],
#                             item["work_doc_code"],
#                             item.get("work_doc_subject"),
#                             item["supply_start_date"],
#                             item["supply_end_date"],
#                             "NEW",
#                             json.dumps(item["raw_payload"], ensure_ascii=False, default=str),
#                         ),
#                     )

#         return {
#             "status": "OK",
#             "message": "Заявка успешно загружена",
#             "application_id": application_id,
#             "items_count": len(items),
#         }

#     except HTTPException:
#         raise
#     except Exception as error:
#         raise HTTPException(status_code=500, detail=f"Ошибка загрузки заявки: {str(error)}")
#     finally:
#         conn.close()


# @router.post("/application-configured/validate")
# def validate_application_configured(payload: ApplicationConfiguredUploadRequest):
#     payload.validate_only = True
#     return upload_application_configured(payload)


# @router.post("/application-configured")
# def upload_application_configured(payload: ApplicationConfiguredUploadRequest):
#     file_path = get_uploaded_file_path(payload.upload_id)

#     parsed = read_application_excel_with_mapping(
#         file_path=file_path,
#         sheet_name=payload.sheet_name,
#         header_row=payload.header_row,
#         column_mapping=payload.column_mapping,
#     )

#     if not parsed["ok"]:
#         raise HTTPException(status_code=400, detail=parsed)

#     items = parsed["items"]
#     skipped_items = []

#     if payload.approved_source_row_nos is not None:
#         approved_set = set(payload.approved_source_row_nos)

#         skipped_items = [
#             item
#             for item in items
#             if item.get("source_row_no") not in approved_set
#         ]

#         items = [
#             item
#             for item in items
#             if item.get("source_row_no") in approved_set
#         ]

#     if not items:
#         return {
#             "status": "NO_APPROVED_ITEMS",
#             "message": "Не выбрано ни одной согласованной позиции для загрузки.",
#             "skipped_count": len(skipped_items),
#             "skipped": [
#                 {
#                     "row": item.get("source_row_no"),
#                     "material_name": item.get("material_name"),
#                     "unit": item.get("unit"),
#                     "quantity": item.get("quantity"),
#                     "work_doc_code": item.get("work_doc_code"),
#                     "work_doc_subject": item.get("work_doc_subject"),
#                 }
#                 for item in skipped_items
#             ],
#         }

#     return create_application_from_items(
#         items=items,
#         source_file_name=payload.upload_id,
#         source_file_path=file_path,
#         raw_payload={
#             "sheet_name": parsed["sheet_name"],
#             "header_row": parsed["header_row"],
#             "column_mapping": parsed["column_mapping"],
#             "source": "excel_configured_upload",
#             "approved_source_row_nos": payload.approved_source_row_nos,
#             "skipped_items": skipped_items,
#         },
#         contract_id=payload.contract_id,
#         work_doc_subject=payload.work_doc_subject,
#         validate_only=payload.validate_only,
#     )


# @router.post("/application-manual")
# def upload_application_manual(payload: ManualApplicationUploadRequest):
#     items = build_manual_items(payload.items)

#     return create_application_from_items(
#         items=items,
#         source_file_name=f"manual-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
#         source_file_path="manual_input",
#         raw_payload={
#             "source": "manual_input",
#             "items": [item.dict() for item in payload.items],
#         },
#         contract_id=payload.contract_id,
#         work_doc_subject=payload.work_doc_subject,
#         validate_only=payload.validate_only,
#     )


# @router.post("/application")
# def upload_application(file: UploadFile = File(...)):
#     """
#     Старый endpoint оставлен для совместимости.
#     Новый интерфейс использует /excel/init, /excel/preview и /application-configured.
#     """
#     upload_id, file_path = save_upload_file(file)

#     parsed = read_application_excel(file_path)

#     if not parsed["ok"]:
#         raise HTTPException(status_code=400, detail=parsed)

#     return create_application_from_items(
#         items=parsed["items"],
#         source_file_name=upload_id,
#         source_file_path=file_path,
#         raw_payload={
#             "sheet_name": parsed.get("sheet_name"),
#             "source": "excel_upload_legacy",
#         },
#     )

import math
import os
import json
import shutil
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

import pandas as pd
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

from app.services.contracts import (
    ensure_application_subject_schema,
    ensure_contract_schema,
    normalize_key,
    normalize_text,
    normalize_work_doc,
    validate_work_doc_rows,
)
from app.services.units import ensure_unit_names_storage
from app.services.excel_templates import build_excel_template_response

router = APIRouter()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


APPLICATION_TEMPLATE_FIELDS = [
    {"key": "material_name", "label": "Наименование позиции", "required": True, "description": "Должно совпадать с материалом в справочнике материалов."},
    {"key": "unit", "label": "Единица измерения", "required": True, "description": "Код или наименование из справочника единиц измерения."},
    {"key": "quantity", "label": "Количество", "required": True, "description": "Число. Можно использовать запятую или точку как десятичный разделитель."},
    {"key": "work_doc_code", "label": "Шифр рабочей документации", "required": True, "description": "Шифр РД должен быть связан с выбранным договором и предметом."},
    {"key": "supply_period", "label": "Дата начала и завершения поставки", "required": True, "description": "Например: 01.07.2026 - 31.07.2026."},
]


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
    contract_id: Optional[str] = None
    validate_only: bool = False
    # Старые поля оставлены для совместимости. В новой логике шифр РД и предмет
    # берутся из строк Excel/ручного ввода, а не из верхних фильтров.
    work_doc_code: Optional[str] = None
    work_doc_subject: Optional[str] = None


class ManualApplicationItem(BaseModel):
    material_name: str
    unit: Optional[str] = None
    quantity: Any
    work_doc_code: Optional[str] = None
    work_doc_subject: Optional[str] = None
    supply_period: Optional[Any] = None


class ManualApplicationUploadRequest(BaseModel):
    items: List[ManualApplicationItem]
    contract_id: Optional[str] = None
    validate_only: bool = False
    work_doc_code: Optional[str] = None
    work_doc_subject: Optional[str] = None


def make_json_safe(value):
    """Убирает NaN/Infinity/NaT из ответов API и raw_payload перед JSON-сериализацией."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]

    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()

    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else None

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    return value


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
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text = str(value).strip().replace(",", ".")

    if not text:
        return None

    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except Exception:
        return None


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
            "work_doc_subject": item.work_doc_subject,
            "supply_period": item.supply_period,
            "source": "manual_input",
        }

        result.append({
            "source_row_no": index,
            "material_name": material_name,
            "unit": clean_manual_value(item.unit),
            "quantity": parse_manual_quantity(item.quantity),
            "work_doc_code": clean_manual_value(item.work_doc_code),
            "work_doc_subject": clean_manual_value(item.work_doc_subject),
            "supply_start_date": supply_start_date,
            "supply_end_date": supply_end_date,
            "raw_payload": make_json_safe(raw_payload),
        })

    return result


def resolve_contract_for_upload(cur, contract_id: str):
    """
    В новой модели contract_id — это один договор.
    РД/предметы берутся из contract_work_doc_subjects.
    """
    cur.execute(
        """
        SELECT
            c.contract_id,
            c.contract_no,
            c.contract_date,
            NULL::text AS contract_appendix
        FROM contracts c
        WHERE c.contract_id = %s
        LIMIT 1
        """,
        (contract_id,),
    )
    selected = cur.fetchone()

    if not selected:
        return None

    cur.execute(
        """
        SELECT
            l.contract_id,
            c.contract_no,
            c.contract_date,
            l.contract_appendix,
            l.work_doc_code,
            l.work_doc_subject,
            l.work_doc_subject AS contract_subject
        FROM contract_work_doc_subjects l
        JOIN contracts c ON c.contract_id = l.contract_id
        JOIN work_document_subjects wds
          ON wds.work_doc_code = l.work_doc_code
         AND wds.work_doc_subject = l.work_doc_subject
        WHERE l.contract_id = %s
        ORDER BY l.work_doc_code, l.work_doc_subject
        """,
        (selected["contract_id"],),
    )
    rows = cur.fetchall()

    selected["contract_rows"] = rows
    selected["contract_subject"] = ", ".join(sorted({row["work_doc_subject"] for row in rows if row.get("work_doc_subject")}))
    return selected


def validate_contract_work_docs(contract, items):
    rows = contract.get("contract_rows") or []
    allowed_pairs = {
        (normalize_work_doc(row.get("work_doc_code")), normalize_key(row.get("work_doc_subject")))
        for row in rows
    }

    missing = []

    for item in items:
        pair = (
            normalize_work_doc(item.get("work_doc_code")),
            normalize_key(item.get("work_doc_subject")),
        )

        if pair not in allowed_pairs:
            missing.append({
                "row": item.get("source_row_no"),
                "material_name": item.get("material_name"),
                "unit": item.get("unit"),
                "quantity": item.get("quantity"),
                "work_doc_code": item.get("work_doc_code"),
                "work_doc_subject": item.get("work_doc_subject"),
                "contract_no": contract.get("contract_no"),
                "error": "В выбранном договоре нет связи с этой парой шифр РД / предмет по РД",
            })

    return missing


def resolve_item_units(cur, items):
    ensure_unit_names_storage(cur)
    cur.execute("SELECT unit_code, unit_name FROM units")
    unit_map = {}
    unit_aliases_by_name = {}

    for row in cur.fetchall():
        code = row.get("unit_code")
        name = row.get("unit_name")
        canonical = code or name
        display_name = name or code
        aliases = set()

        if code:
            unit_map[normalize_key(code)] = {"code": canonical, "name": display_name}
            aliases.add(code)
        if name:
            unit_map[normalize_key(name)] = {"code": canonical, "name": display_name}
            aliases.add(name)

        if canonical:
            unit_aliases_by_name.setdefault(canonical, set()).update(aliases)

    missing = []

    for item in items:
        unit_value = item.get("unit")
        unit_key = normalize_key(unit_value)

        if not unit_key or unit_key not in unit_map:
            missing.append({
                "row": item.get("source_row_no"),
                "material_name": item.get("material_name"),
                "unit": unit_value,
                "quantity": item.get("quantity"),
                "work_doc_code": item.get("work_doc_code"),
                "work_doc_subject": item.get("work_doc_subject"),
                "error": "Единица измерения не найдена в справочнике",
            })
            continue

        resolved_unit = unit_map[unit_key]
        item["raw_payload"] = {
            **(item.get("raw_payload") or {}),
            "source_unit": unit_value,
            "resolved_unit": resolved_unit["name"],
            "resolved_unit_code": resolved_unit["code"],
        }
        item["unit"] = resolved_unit["code"]

    return missing


def build_unit_alias_lookup(cur):
    ensure_unit_names_storage(cur)
    cur.execute("SELECT unit_code, unit_name FROM units")
    unit_to_canonical = {}
    canonical_to_aliases = {}

    for row in cur.fetchall():
        code = row.get("unit_code")
        name = row.get("unit_name")
        canonical = code or name
        aliases = {value for value in [code, name] if value}

        if not canonical:
            continue

        canonical_to_aliases.setdefault(normalize_key(canonical), set()).update(aliases | {canonical})

        for alias in aliases | {canonical}:
            unit_to_canonical[normalize_key(alias)] = canonical

    return unit_to_canonical, canonical_to_aliases


def build_material_map(cur):
    """Материалы могли быть сохранены как с кодами единиц (U19), так и с названиями (шт).
    Для проверки строим ключи по обоим вариантам, чтобы не получать ложную ошибку.
    """
    unit_to_canonical, canonical_to_aliases = build_unit_alias_lookup(cur)
    cur.execute("SELECT material_id, material_name, unit FROM materials")

    material_map = {}

    for material in cur.fetchall():
        material_name_key = normalize(material["material_name"])
        raw_unit = material.get("unit")
        raw_unit_key = normalize_key(raw_unit)
        canonical = unit_to_canonical.get(raw_unit_key, raw_unit)
        alias_values = {raw_unit, canonical}

        if canonical:
            alias_values.update(canonical_to_aliases.get(normalize_key(canonical), set()))

        for alias in alias_values:
            if alias is None:
                continue
            key = f"{material_name_key}|{normalize(alias)}"
            material_map[key] = material

    return material_map


@router.get("/application-template")
def download_application_template():
    return build_excel_template_response(
        filename="application-template.xlsx",
        sheet_title="Шаблон заявки",
        fields=APPLICATION_TEMPLATE_FIELDS,
        example_row={
            "material_name": "Кабель силовой",
            "unit": "м",
            "quantity": "100",
            "work_doc_code": "РД-001",
            "supply_period": "01.07.2026 - 31.07.2026",
        },
        description=(
            "Заполните позиции заявки на первом листе. Перед загрузкой выберите договор и предмет в интерфейсе. "
            "Excel-загрузка и ручной ввод проходят через одну backend-проверку."
        ),
    )


@router.post("/excel/init")
def init_excel_upload(file: UploadFile = File(...)):
    upload_id, file_path = save_upload_file(file)

    try:
        sheets_info = get_excel_sheets(file_path)
        return make_json_safe({
            "status": "OK",
            "upload_id": upload_id,
            "original_filename": file.filename,
            "sheets": sheets_info["sheets"],
        })
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
        preview_rows=5000,
    )

    if not result["ok"]:
        raise HTTPException(status_code=400, detail=make_json_safe(result))

    return make_json_safe(result)


def create_application_from_items(
    items: list,
    source_file_name: str,
    source_file_path: str,
    raw_payload: dict,
    contract_id: Optional[str] = None,
    work_doc_subject: Optional[str] = None,
    validate_only: bool = False,
):
    if not items:
        raise HTTPException(status_code=400, detail="На выбранном листе не найдено ни одной позиции")

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                ensure_contract_schema(cur)
                ensure_application_subject_schema(cur)

                if not contract_id:
                    return make_json_safe({
                        "status": "CONTRACT_NOT_SELECTED",
                        "message": "Перед загрузкой заявки выберите договор из реестра договоров.",
                        "redirect_url": "/contracts",
                    })

                contract = resolve_contract_for_upload(cur, contract_id=contract_id)

                if not contract:
                    return make_json_safe({
                        "status": "CONTRACT_NOT_FOUND",
                        "message": "Выбранный договор не найден в реестре договоров.",
                        "redirect_url": "/contracts",
                    })

                selected_subject = normalize_text(work_doc_subject)

                if not selected_subject:
                    return make_json_safe({
                        "status": "CONTRACT_SUBJECT_NOT_SELECTED",
                        "message": "Перед загрузкой заявки выберите предмет, привязанный к договору.",
                        "redirect_url": "/contracts",
                    })

                for item in items:
                    item["work_doc_subject"] = selected_subject
                    item["raw_payload"] = {
                        **(item.get("raw_payload") or {}),
                        "selected_work_doc_subject": selected_subject,
                    }

                missing_work_docs = validate_work_doc_rows(cur, items)

                if missing_work_docs:
                    return make_json_safe({
                        "status": "WORK_DOCS_NOT_FOUND",
                        "message": "В заявке есть строки с шифрами РД/предметами, которых нет в справочнике.",
                        "redirect_url": "/dict/work-doc-subjects",
                        "missing_work_docs": missing_work_docs,
                    })

                missing_contract_links = validate_contract_work_docs(contract, items)

                if missing_contract_links:
                    return make_json_safe({
                        "status": "CONTRACT_WORK_DOCS_NOT_LINKED",
                        "message": "В выбранном договоре нет связей с некоторыми РД/предметами из заявки.",
                        "redirect_url": "/contracts",
                        "missing_contract_work_docs": missing_contract_links,
                    })

                missing_units = resolve_item_units(cur, items)

                if missing_units:
                    return make_json_safe({
                        "status": "UNITS_NOT_FOUND",
                        "message": "В заявке есть единицы измерения, которых нет в справочнике.",
                        "redirect_url": "/dict/units",
                        "missing_units": missing_units,
                    })

                material_map = build_material_map(cur)

                missing = []
                material_unit_conflicts = []
                invalid_rows = []

                for item in items:
                    key = f"{normalize(item['material_name'])}|{normalize(item['unit'])}"
                    found = material_map.get(key)

                    if not found:
                        cur.execute(
                            """
                            SELECT
                                m.material_id,
                                m.material_name,
                                COALESCE(u.unit_name, m.unit) AS unit
                            FROM materials m
                            LEFT JOIN units u
                                ON lower(btrim(u.unit_code)) = lower(btrim(m.unit))
                                OR lower(btrim(u.unit_name)) = lower(btrim(m.unit))
                            WHERE lower(btrim(m.material_name)) = lower(btrim(%s))
                            ORDER BY m.material_id
                            LIMIT 10
                            """,
                            (item["material_name"],),
                        )
                        same_name_matches = cur.fetchall()

                        if same_name_matches:
                            material_unit_conflicts.append({
                                "row": item["source_row_no"],
                                "material_name": item["material_name"],
                                "unit": (item.get("raw_payload") or {}).get("resolved_unit") or item["unit"],
                                "work_doc_code": item.get("work_doc_code"),
                                "work_doc_subject": item.get("work_doc_subject"),
                                "error": "В справочнике уже есть материал с таким наименованием, но с другой единицей измерения.",
                                "matches": same_name_matches,
                            })
                        else:
                            missing.append({
                                "row": item["source_row_no"],
                                "material_name": item["material_name"],
                                "unit": (item.get("raw_payload") or {}).get("resolved_unit") or item["unit"],
                                "work_doc_code": item.get("work_doc_code"),
                                "work_doc_subject": item.get("work_doc_subject"),
                            })
                    else:
                        item["material_id"] = found["material_id"]

                    # Проверка обязательного количества намеренно убрана.
                    # Количество нормализуется на этапе чтения Excel и может быть None.
                    # Если строка без количества всё же будет отправлена на фактическую загрузку,
                    # её может отклонить ограничение БД purchase_application_items.quantity.

                    if item.get("supply_start_date") and item.get("supply_end_date"):
                        if item["supply_start_date"] > item["supply_end_date"]:
                            invalid_rows.append({
                                "row": item["source_row_no"],
                                "material_name": item["material_name"],
                                "unit": (item.get("raw_payload") or {}).get("resolved_unit") or item["unit"],
                                "error": "Дата начала поставки больше даты окончания поставки",
                            })

                if material_unit_conflicts:
                    return make_json_safe({
                        "status": "MATERIAL_UNIT_CONFLICTS",
                        "message": "В заявке есть материалы, которые уже заведены в справочнике с другой единицей измерения.",
                        "redirect_url": "/dict/materials",
                        "material_unit_conflicts": material_unit_conflicts,
                    })

                if missing:
                    return make_json_safe({
                        "status": "MATERIALS_NOT_FOUND",
                        "message": "В справочнике отсутствуют материалы с указанными единицами измерения.",
                        "redirect_url": "/dict/materials",
                        "missing": missing,
                    })

                if invalid_rows:
                    return make_json_safe({
                        "status": "VALIDATION_ERROR",
                        "message": "В строках заявки есть ошибки",
                        "errors": invalid_rows,
                    })

                if validate_only:
                    return make_json_safe({
                        "status": "VALIDATION_OK",
                        "message": "Проверка успешно пройдена. Можно загружать заявку в базу.",
                        "items_count": len(items),
                        "contract_id": contract["contract_id"],
                        "contract_no": contract["contract_no"],
                        "work_doc_subject": selected_subject,
                    })

                distinct_subjects = []
                distinct_pairs = []
                seen_subjects = set()
                seen_pairs = set()

                for item in items:
                    subject = normalize_text(item.get("work_doc_subject"))
                    pair = (
                        normalize_work_doc(item.get("work_doc_code")),
                        normalize_key(item.get("work_doc_subject")),
                    )

                    if subject and normalize_key(subject) not in seen_subjects:
                        distinct_subjects.append(subject)
                        seen_subjects.add(normalize_key(subject))

                    if pair not in seen_pairs:
                        distinct_pairs.append({
                            "work_doc_code": item.get("work_doc_code"),
                            "work_doc_subject": item.get("work_doc_subject"),
                        })
                        seen_pairs.add(pair)

                application_no = f"AUTO-{date.today().isoformat()}-{source_file_name}"
                contract_subject = ", ".join(distinct_subjects) if distinct_subjects else contract.get("contract_subject")

                cur.execute(
                    """
                    INSERT INTO purchase_applications (
                        application_no,
                        application_date,
                        construction_object,
                        contract_id,
                        contract_no,
                        contract_date,
                        contract_appendix,
                        contract_subject,
                        source_file_name,
                        source_file_path,
                        raw_payload
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    RETURNING application_id
                    """,
                    (
                        application_no,
                        date.today(),
                        None,
                        contract["contract_id"],
                        contract["contract_no"],
                        contract["contract_date"],
                        contract["contract_appendix"],
                        contract_subject,
                        source_file_name,
                        source_file_path,
                        json.dumps(
                            make_json_safe({
                                **raw_payload,
                                "contract_id": contract["contract_id"],
                                "contract_no": contract["contract_no"],
                                "contract_date": contract["contract_date"],
                                "contract_appendix": contract["contract_appendix"],
                                "contract_subject": contract_subject,
                                "work_doc_pairs": distinct_pairs,
                            }),
                            ensure_ascii=False,
                            default=str,
                        ),
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
                            work_doc_subject,
                            supply_start_date,
                            supply_end_date,
                            processing_status,
                            raw_payload
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                        """,
                        (
                            application_id,
                            item["source_row_no"],
                            item["material_id"],
                            item["material_name"],
                            item["unit"],
                            item["quantity"],
                            item["work_doc_code"],
                            item.get("work_doc_subject"),
                            item["supply_start_date"],
                            item["supply_end_date"],
                            "NEW",
                            json.dumps(make_json_safe(item["raw_payload"]), ensure_ascii=False, default=str),
                        ),
                    )

        return make_json_safe({
            "status": "OK",
            "message": "Заявка успешно загружена",
            "application_id": application_id,
            "items_count": len(items),
        })

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки заявки: {str(error)}")
    finally:
        conn.close()


@router.post("/application-configured/validate")
def validate_application_configured(payload: ApplicationConfiguredUploadRequest):
    payload.validate_only = True
    return make_json_safe(upload_application_configured(payload))


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
        raise HTTPException(status_code=400, detail=make_json_safe(parsed))

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
        return make_json_safe({
            "status": "NO_APPROVED_ITEMS",
            "message": "Не выбрано ни одной согласованной позиции для загрузки.",
            "skipped_count": len(skipped_items),
            "skipped": [
                {
                    "row": item.get("source_row_no"),
                    "material_name": item.get("material_name"),
                    "unit": item.get("unit"),
                    "quantity": item.get("quantity"),
                    "work_doc_code": item.get("work_doc_code"),
                    "work_doc_subject": item.get("work_doc_subject"),
                }
                for item in skipped_items
            ],
        })

    return make_json_safe(create_application_from_items(
        items=items,
        source_file_name=payload.upload_id,
        source_file_path=file_path,
        raw_payload=make_json_safe({
            "sheet_name": parsed["sheet_name"],
            "header_row": parsed["header_row"],
            "column_mapping": parsed["column_mapping"],
            "source": "excel_configured_upload",
            "approved_source_row_nos": payload.approved_source_row_nos,
            "skipped_items": skipped_items,
        }),
        contract_id=payload.contract_id,
        work_doc_subject=payload.work_doc_subject,
        validate_only=payload.validate_only,
    ))


@router.post("/application-manual")
def upload_application_manual(payload: ManualApplicationUploadRequest):
    items = build_manual_items(payload.items)

    return make_json_safe(create_application_from_items(
        items=items,
        source_file_name=f"manual-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        source_file_path="manual_input",
        raw_payload=make_json_safe({
            "source": "manual_input",
            "items": [item.dict() for item in payload.items],
        }),
        contract_id=payload.contract_id,
        work_doc_subject=payload.work_doc_subject,
        validate_only=payload.validate_only,
    ))


@router.post("/application")
def upload_application(file: UploadFile = File(...)):
    """
    Старый endpoint оставлен для совместимости.
    Новый интерфейс использует /excel/init, /excel/preview и /application-configured.
    """
    upload_id, file_path = save_upload_file(file)

    parsed = read_application_excel(file_path)

    if not parsed["ok"]:
        raise HTTPException(status_code=400, detail=make_json_safe(parsed))

    return make_json_safe(create_application_from_items(
        items=parsed["items"],
        source_file_name=upload_id,
        source_file_path=file_path,
        raw_payload={
            "sheet_name": parsed.get("sheet_name"),
            "source": "excel_upload_legacy",
        },
    ))

