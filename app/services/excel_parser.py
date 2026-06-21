import re
from datetime import datetime, date
from typing import Any
import pandas as pd

APPLICATION_SHEET_NAME = "Заявка"


def normalize(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip().lower()


def safe_value(value: Any):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    return value


def parse_supply_period(value: Any):
    if value is None:
        return None, None

    try:
        if pd.isna(value):
            return None, None
    except Exception:
        pass

    if isinstance(value, datetime):
        d = value.date()
        return d, d

    if isinstance(value, date):
        return value, value

    text = str(value).strip()
    matches = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", text)

    if not matches:
        return None, None

    def to_date(parts):
        dd, mm, yyyy = parts
        return date(int(yyyy), int(mm), int(dd))

    start = to_date(matches[0])
    end = to_date(matches[1]) if len(matches) > 1 else start
    return start, end


def get_excel_sheets(file_path: str):
    excel = pd.ExcelFile(file_path)
    return {"sheets": excel.sheet_names}


def get_sheet_preview(
    file_path: str,
    sheet_name: str,
    header_row: int = 1,
    preview_rows: int = 500,
):
    """
    header_row — номер строки в Excel, начиная с 1.
    Например: 1 = первая строка листа, 2 = вторая строка листа.

    __source_row_no — фактический номер строки в Excel.
    Он нужен frontend-у, чтобы пользователь мог согласовать конкретные строки.
    """
    excel = pd.ExcelFile(file_path)

    if sheet_name not in excel.sheet_names:
        return {
            "ok": False,
            "error": f'Лист "{sheet_name}" не найден',
            "available_sheets": excel.sheet_names,
        }

    header_index = max(int(header_row) - 1, 0)

    df = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=header_index,
    )

    df = df.dropna(how="all")
    columns = [str(col).strip() for col in df.columns]

    preview = []
    for row_offset, (_, row) in enumerate(df.head(preview_rows).iterrows(), start=1):
        source_row_no = int(header_row) + row_offset

        item = {
            "__source_row_no": source_row_no,
            **{
                str(col).strip(): safe_value(row[col])
                for col in df.columns
            }
        }

        preview.append(item)

    return {
        "ok": True,
        "sheet_name": sheet_name,
        "header_row": header_row,
        "columns": columns,
        "preview": preview,
    }

def read_application_excel_with_mapping(
    file_path: str,
    sheet_name: str,
    header_row: int,
    column_mapping: dict,
):
    """
    column_mapping пример:
    {
      "material_name": "Наименование позиции",
      "unit": "Единица измерения",
      "quantity": "Количество",
      "work_doc_code": "Шифр рабочей документации",
      "supply_period": "Дата начала и завершения поставки"
    }
    """
    excel = pd.ExcelFile(file_path)

    if sheet_name not in excel.sheet_names:
        return {
            "ok": False,
            "error": f'Лист "{sheet_name}" не найден',
            "available_sheets": excel.sheet_names,
        }

    required_fields = [
        "material_name",
        "unit",
        "quantity",
        "work_doc_code",
        "supply_period",
    ]

    missing_mapping = [
        field for field in required_fields
        if not column_mapping.get(field)
    ]

    if missing_mapping:
        return {
            "ok": False,
            "error": "Не выбраны обязательные столбцы",
            "missing_mapping": missing_mapping,
        }

    header_index = max(int(header_row) - 1, 0)

    df = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=header_index,
    )

    df = df.dropna(how="all")
    columns = [str(col).strip() for col in df.columns]

    for field, excel_column in column_mapping.items():
        if excel_column and excel_column not in columns:
            return {
                "ok": False,
                "error": f'Столбец "{excel_column}" не найден на листе "{sheet_name}"',
                "columns": columns,
            }

    items = []

    for row_index, row in enumerate(df.to_dict(orient="records"), start=int(header_row) + 1):
        material_col = column_mapping["material_name"]
        unit_col = column_mapping["unit"]
        quantity_col = column_mapping["quantity"]
        work_doc_col = column_mapping["work_doc_code"]
        work_doc_subject_col = column_mapping.get("work_doc_subject")
        supply_period_col = column_mapping["supply_period"]

        material_name = row.get(material_col)
        unit = row.get(unit_col)
        quantity = row.get(quantity_col)
        work_doc_code = row.get(work_doc_col)
        work_doc_subject = row.get(work_doc_subject_col) if work_doc_subject_col else None
        supply_period = row.get(supply_period_col)

        if material_name is None or str(material_name).strip() == "":
            continue

        try:
            quantity_value = float(quantity) if quantity is not None and str(quantity).strip() != "" else 0
        except Exception:
            quantity_value = 0

        supply_start_date, supply_end_date = parse_supply_period(supply_period)

        raw_payload = {
            str(k): safe_value(v)
            for k, v in row.items()
        }

        items.append({
            "source_row_no": row_index,
            "material_name": str(material_name).strip(),
            "unit": str(unit).strip() if unit is not None else None,
            "quantity": quantity_value,
            "work_doc_code": str(work_doc_code).strip() if work_doc_code else None,
            "work_doc_subject": str(work_doc_subject).strip() if work_doc_subject else None,
            "supply_start_date": supply_start_date,
            "supply_end_date": supply_end_date,
            "raw_payload": raw_payload,
        })

    return {
        "ok": True,
        "items": items,
        "sheet_name": sheet_name,
        "header_row": header_row,
        "columns": columns,
        "column_mapping": column_mapping,
    }


def read_application_excel(file_path: str):
    """
    Совместимость со старым endpoint /api/upload/application.
    По-прежнему ищет лист "Заявка" и стандартные названия колонок.
    """
    column_mapping = {
        "material_name": "Наименование позиции",
        "unit": "Единица измерения",
        "quantity": "Количество",
        "work_doc_code": "Шифр рабочей документации",
        "supply_period": "Дата начала и завершения поставки",
    }

    return read_application_excel_with_mapping(
        file_path=file_path,
        sheet_name=APPLICATION_SHEET_NAME,
        header_row=1,
        column_mapping=column_mapping,
    )
