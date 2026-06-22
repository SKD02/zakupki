import re
from datetime import date, datetime
from typing import Any, Dict, List

import pandas as pd

from app.services.units import ensure_unit_names_storage, resolve_unit_code
from app.services.suppliers import ensure_supplier_id_schema, next_supplier_id, resolve_okved2_code, is_missing_reference


DICTIONARY_IMPORT_FIELDS = {
    "materials": [
        {"key": "material_name", "label": "Наименование материала", "required": True},
        {"key": "unit", "label": "Единица измерения"},
        {"key": "description", "label": "Описание"},
    ],
    "okpd2": [
        {"key": "okpd2_code", "label": "Код ОКПД2", "required": True},
        {"key": "name_okpd2", "label": "Наименование ОКПД2", "required": True},
    ],
    "okved2": [
        {"key": "okved2_code", "label": "Код ОКВЭД2", "required": True},
        {"key": "name_okved2", "label": "Наименование ОКВЭД2", "required": True},
    ],
    "user-groups": [
        {"key": "name_possition", "label": "Наименование группы", "required": True},
        {"key": "description", "label": "Описание"},
    ],
    "units": [
        {"key": "unit_name", "label": "Наименование единицы измерения", "required": True},
        {"key": "description", "label": "Описание"},
    ],
    "work-doc-subjects": [
        {"key": "work_doc_code", "label": "Шифр РД", "required": True},
        {"key": "work_doc_subject", "label": "Предмет по РД", "required": True},
        {"key": "description", "label": "Описание"},
    ],
    "suppliers": [
        {"key": "inn", "label": "ИНН", "required": True},
        {"key": "name", "label": "Наименование поставщика", "required": True},
        {"key": "short_name", "label": "Краткое наименование"},
        {"key": "registration_number", "label": "Регистрационный номер"},
        {"key": "registration_date", "label": "Дата регистрации"},
        {"key": "address", "label": "Адрес"},
        {"key": "management", "label": "Руководитель"},
        {"key": "management_position", "label": "Должность руководителя"},
        {"key": "okved2_code", "label": "ОКВЭД2"},
        {"key": "organizational_legal_form", "label": "ОПФ"},
        {"key": "ownership_form", "label": "Форма собственности"},
        {"key": "company_size", "label": "Размер компании"},
        {"key": "phone", "label": "Телефон"},
        {"key": "email", "label": "Email"},
        {"key": "website", "label": "Сайт"},
        {"key": "tax_regime", "label": "Налоговый режим"},
        {"key": "report_year", "label": "Год отчётности"},
        
        {"key": "average_headcount", "label": "Среднесписочная численность"},
        {"key": "credit_limit_rub", "label": "Кредитный лимит, руб."},
        {"key": "pending_claims_as_defendant_rub", "label": "Иски в роли ответчика, руб."},
        {"key": "enforcement_proceedings_rub", "label": "Исполнительные производства, руб."},
        {"key": "charter_capital_rub", "label": "Уставный капитал, руб."},
        
        {"key": "income_rub", "label": "Доходы, руб."},
        {"key": "expenses_rub", "label": "Расходы, руб."},
        {"key": "taxes_rub", "label": "Налоги, руб."},
        {"key": "total_assets_rub", "label": "Активы всего, руб."},
        {"key": "retained_earnings_uncovered_loss_rub", "label": "Нераспределённая прибыль / непокрытый убыток, руб."},
        {"key": "capital_and_reserves_rub", "label": "Капитал и резервы, руб."},
        {"key": "long_term_liabilities_rub", "label": "Долгосрочные обязательства, руб."},
        {"key": "short_term_liabilities_rub", "label": "Краткосрочные обязательства, руб."},
        
        {"key": "revenue_rub", "label": "Выручка, руб."},
        {"key": "profit_loss_from_sales_rub", "label": "Прибыль/убыток от продаж, руб."},
        {"key": "net_profit_loss_rub", "label": "Чистая прибыль/убыток, руб."},
    ],
}

MISSING_VALUE_MARKERS = {"#н/д", "н/д", "#n/a", "n/a", "na", "nan", "none", "null", "-", "—"}


def get_dictionary_import_fields(dictionary_type: str):
    fields = DICTIONARY_IMPORT_FIELDS.get(dictionary_type)

    if not fields:
        raise ValueError(f"Импорт для справочника {dictionary_type} не настроен")

    return fields


def _clean(value: Any):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None

    if text.lower().replace("ё", "е") in MISSING_VALUE_MARKERS:
        return None

    return text


def _as_int(value: Any):
    value = _clean(value)
    if value is None:
        return None

    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return None


def _as_float(value: Any):
    value = _clean(value)
    if value is None:
        return None

    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except Exception:
        return None


def _normalize(value: Any):
    return str(value or "").strip().lower().replace("ё", "е")


def _normalize_search_text(value: Any) -> str:
    value = str(value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _format_existing_matches(rows: List[dict], label: str = "Найдено") -> str:
    if not rows:
        return ""
    formatted = []
    for row in rows[:5]:
        parts = []
        for key, value in row.items():
            if value not in (None, ""):
                parts.append(f"{key}: {value}")
        formatted.append("; ".join(parts) or str(row))
    return f" {label}: " + " | ".join(formatted)


def _fetch_user_group_similar_matches(cur, name: str) -> List[dict]:
    normalized_input = _normalize_search_text(name)
    input_words = [word for word in normalized_input.split(" ") if len(word) >= 4]
    if not input_words:
        return []
    cur.execute(
        """
        SELECT id_possition, name_possition, description
        FROM user_material_groups
        ORDER BY id_possition
        """
    )
    similar_matches = []
    for row in cur.fetchall():
        normalized_existing = _normalize_search_text(row.get("name_possition"))
        matched_words = [word for word in input_words if word in normalized_existing]
        existing_words = [word for word in normalized_existing.split(" ") if len(word) >= 4]
        reverse_matched_words = [word for word in existing_words if word in normalized_input]
        if matched_words or reverse_matched_words:
            similar_matches.append({
                **row,
                "match_reason": (
                    "Найдено частичное совпадение по словам: "
                    + ", ".join(sorted(set(matched_words + reverse_matched_words)))
                ),
            })
    return similar_matches[:10]


def _next_masked_id(cur, table: str, id_column: str, prefix: str, digits: int):
    cur.execute(
        f"""
        SELECT {id_column} AS id_value
        FROM {table}
        WHERE {id_column} ~ %s
        ORDER BY {id_column} DESC
        LIMIT 1
        """,
        (f"^{prefix}[0-9]{{{digits}}}$",),
    )

    row = cur.fetchone()

    if not row:
        return f"{prefix}{1:0{digits}d}"

    import re

    match = re.search(r"(\d+)$", row["id_value"] or "")
    next_no = int(match.group(1)) + 1 if match else 1
    return f"{prefix}{next_no:0{digits}d}"


def read_dictionary_excel_rows(
    file_path: str,
    sheet_name: str,
    header_row: int,
    column_mapping: Dict[str, str],
    fields: List[Dict[str, Any]],
):
    required_keys = [field["key"] for field in fields if field.get("required")]

    missing_mapping = [
        key
        for key in required_keys
        if not column_mapping.get(key)
    ]

    if missing_mapping:
        raise ValueError(f"Не выбраны обязательные столбцы: {', '.join(missing_mapping)}")

    excel = pd.ExcelFile(file_path)

    if sheet_name not in excel.sheet_names:
        raise ValueError(f'Лист "{sheet_name}" не найден')

    header_index = max(int(header_row) - 1, 0)

    df = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=header_index,
    )

    df = df.dropna(how="all")

    columns = [str(column).strip() for column in df.columns]

    for field_key, excel_column in column_mapping.items():
        if excel_column and excel_column not in columns:
            raise ValueError(f'Столбец "{excel_column}" не найден на листе "{sheet_name}"')

    rows = []

    for row_index, row in enumerate(df.to_dict(orient="records"), start=int(header_row) + 1):
        item = {"__source_row_no": row_index}

        for field_key, excel_column in column_mapping.items():
            if excel_column:
                item[field_key] = _clean(row.get(excel_column))

        has_any_value = any(
            value not in (None, "")
            for key, value in item.items()
            if key != "__source_row_no"
        )

        if has_any_value:
            rows.append(item)

    return rows


def _validate_required(row: dict, fields: List[Dict[str, Any]]):
    missed = []

    for field in fields:
        if field.get("required") and not _clean(row.get(field["key"])):
            missed.append(field["label"])

    return missed


def _resolve_unit_info(cur, unit_value):
    unit_value = _clean(unit_value)

    if not unit_value:
        return None

    ensure_unit_names_storage(cur)
    unit_code = resolve_unit_code(cur, unit_value)

    if not unit_code:
        raise ValueError(
            f'Единица измерения "{unit_value}" отсутствует в справочнике. '
            "Сначала импортируйте или добавьте её во вкладке Единицы измерения."
        )

    cur.execute(
        """
        SELECT unit_code, unit_name
        FROM units
        WHERE lower(btrim(unit_code)) = lower(btrim(%s))
        LIMIT 1
        """,
        (unit_code,),
    )
    unit = cur.fetchone() or {"unit_code": unit_code, "unit_name": unit_code}

    return {
        "code": unit.get("unit_code") or unit_code,
        "name": unit.get("unit_name") or unit.get("unit_code") or unit_code,
        "source": unit_value,
    }


def _resolve_unit(cur, unit_value):
    unit = _resolve_unit_info(cur, unit_value)
    return unit["code"] if unit else None


def _unit_alias_set(*values):
    aliases = set()

    for value in values:
        cleaned = _clean(value)
        if cleaned is not None:
            aliases.add(_normalize(cleaned))

    if not aliases:
        aliases.add("")

    return aliases


def _sanitize_material_match(row: dict) -> dict:
    return {
        "material_id": row.get("material_id"),
        "material_name": row.get("material_name"),
        "unit": row.get("unit"),
        "description": row.get("description"),
    }


def find_material_matches_for_unit(cur, material_name: str, unit_value):
    """Возвращает совпадения материала с учётом старого и нового формата хранения unit.

    В старых данных unit мог храниться как наименование ("шт"), а в новых — как код ("U19").
    Поэтому сравниваем не только сырое значение materials.unit, но и связанное наименование
    из справочника единиц измерения. Это делает Excel-импорт и ручной ввод одинаковыми.
    """
    material_name = _clean(material_name)
    unit_info = _resolve_unit_info(cur, unit_value)
    input_aliases = _unit_alias_set(
        unit_info.get("code") if unit_info else None,
        unit_info.get("name") if unit_info else None,
        unit_info.get("source") if unit_info else unit_value,
    )

    cur.execute(
        """
        SELECT
            m.material_id,
            m.material_name,
            COALESCE(u.unit_name, m.unit) AS unit,
            m.description,
            m.unit AS _unit_raw,
            u.unit_code AS _unit_code,
            u.unit_name AS _unit_name
        FROM materials m
        LEFT JOIN units u
            ON lower(btrim(u.unit_code)) = lower(btrim(m.unit))
            OR lower(btrim(u.unit_name)) = lower(btrim(m.unit))
        WHERE lower(btrim(m.material_name)) = lower(btrim(%s))
        ORDER BY m.material_id
        """,
        (material_name,),
    )

    same_unit = []
    other_unit = []

    for row in cur.fetchall():
        existing_aliases = _unit_alias_set(
            row.get("_unit_raw"),
            row.get("_unit_code"),
            row.get("_unit_name"),
            row.get("unit"),
        )
        sanitized = _sanitize_material_match(row)

        if input_aliases & existing_aliases:
            same_unit.append(sanitized)
        else:
            other_unit.append(sanitized)

    return {
        "unit_code": unit_info.get("code") if unit_info else None,
        "unit_name": unit_info.get("name") if unit_info else None,
        "same_unit": same_unit,
        "other_unit": other_unit,
    }

def _import_unit(cur, row):
    unit_name = _clean(row.get("unit_name"))
    description = _clean(row.get("description"))
    unit_code = _clean(row.get("unit_code"))

    if unit_code:
        unit_code = unit_code.upper()
        cur.execute(
            """
            SELECT unit_code, unit_name, description
            FROM units
            WHERE lower(btrim(unit_code)) = lower(btrim(%s))
            LIMIT 1
            """,
            (unit_code,),
        )
        same_code = cur.fetchone()
        if same_code:
            raise ValueError(
                "Единица измерения с таким кодом уже есть в справочнике."
                + _format_existing_matches([same_code])
            )

    cur.execute(
        """
        SELECT unit_code, unit_name, description
        FROM units
        WHERE lower(btrim(unit_name)) = lower(btrim(%s))
        ORDER BY unit_code
        LIMIT 1
        """,
        (unit_name,),
    )
    same_name = cur.fetchone()
    if same_name:
        raise ValueError(
            "Единица измерения с таким наименованием уже есть в справочнике."
            + _format_existing_matches([same_name])
        )

    unit_code = unit_code or _next_masked_id(cur, "units", "unit_code", "U", 2)
    cur.execute(
        """
        INSERT INTO units (unit_code, unit_name, description)
        VALUES (%s,%s,%s)
        """,
        (unit_code, unit_name, description),
    )
    return "inserted"


def _import_material(cur, row):
    # ID материала в Excel больше не нужен: если колонка не настроена, ID генерируется автоматически.
    # Оставляем чтение material_id только для обратной совместимости старых пользовательских файлов.
    material_id = _clean(row.get("material_id"))
    material_name = _clean(row.get("material_name"))
    description = _clean(row.get("description"))

    if material_id:
        cur.execute(
            """
            SELECT material_id, material_name, unit, description
            FROM materials
            WHERE btrim(material_id) = btrim(%s)
            LIMIT 1
            """,
            (material_id,),
        )
        same_id = cur.fetchone()
        if same_id:
            raise ValueError(
                "Материал с таким ID уже есть в справочнике."
                + _format_existing_matches([same_id])
            )

    matches = find_material_matches_for_unit(cur, material_name, row.get("unit"))
    unit = matches["unit_code"]

    if matches["same_unit"]:
        raise ValueError(
            "Материал с таким наименованием и единицей измерения уже есть в справочнике."
            + _format_existing_matches(matches["same_unit"])
        )

    if matches["other_unit"]:
        raise ValueError(
            "Материал с таким наименованием уже есть в справочнике, но с другой единицей измерения."
            + _format_existing_matches(matches["other_unit"])
        )

    material_id = material_id or _next_masked_id(cur, "materials", "material_id", "M", 8)
    cur.execute(
        """
        INSERT INTO materials (material_id, material_name, unit, description)
        VALUES (%s,%s,%s,%s)
        """,
        (material_id, material_name, unit, description),
    )
    return "inserted"

def _import_okpd2(cur, row):
    code = _clean(row.get("okpd2_code"))
    name = _clean(row.get("name_okpd2"))

    cur.execute(
        """
        SELECT okpd2_code
        FROM okpd2
        WHERE btrim(okpd2_code) = btrim(%s)
        LIMIT 1
        """,
        (code,),
    )

    existing = cur.fetchone()

    if existing:
        cur.execute(
            """
            UPDATE okpd2
            SET name_okpd2 = %s
            WHERE okpd2_code = %s
            """,
            (name, existing["okpd2_code"]),
        )
        return "updated"

    cur.execute(
        """
        INSERT INTO okpd2 (okpd2_code, name_okpd2)
        VALUES (%s,%s)
        """,
        (code, name),
    )

    return "inserted"


def _import_okved2(cur, row):
    code = _clean(row.get("okved2_code"))
    name = _clean(row.get("name_okved2"))

    cur.execute(
        """
        SELECT okved2_code
        FROM okved2
        WHERE btrim(okved2_code) = btrim(%s)
        LIMIT 1
        """,
        (code,),
    )

    existing = cur.fetchone()

    if existing:
        cur.execute(
            """
            UPDATE okved2
            SET name_okved2 = %s
            WHERE okved2_code = %s
            """,
            (name, existing["okved2_code"]),
        )
        return "updated"

    cur.execute(
        """
        INSERT INTO okved2 (okved2_code, name_okved2)
        VALUES (%s,%s)
        """,
        (code, name),
    )

    return "inserted"


def _normalize_work_doc(value):
    value = _clean(value)
    return value.upper() if value else None


def _import_work_doc_subject(cur, row):
    work_doc_code = _normalize_work_doc(row.get("work_doc_code"))
    work_doc_subject = _clean(row.get("work_doc_subject"))
    description = _clean(row.get("description"))

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
        SELECT work_doc_code, work_doc_subject
        FROM work_document_subjects
        WHERE lower(btrim(work_doc_code)) = lower(btrim(%s))
          AND lower(btrim(work_doc_subject)) = lower(btrim(%s))
        LIMIT 1
        """,
        (work_doc_code, work_doc_subject),
    )

    existing = cur.fetchone()

    if existing:
        cur.execute(
            """
            UPDATE work_document_subjects
            SET description = COALESCE(%s, description),
                updated_at = now()
            WHERE work_doc_code = %s
              AND work_doc_subject = %s
            """,
            (description, existing["work_doc_code"], existing["work_doc_subject"]),
        )
        return "updated"

    cur.execute(
        """
        INSERT INTO work_document_subjects (
            work_doc_code,
            work_doc_subject,
            description,
            updated_at
        )
        VALUES (%s,%s,%s,now())
        """,
        (work_doc_code, work_doc_subject, description),
    )

    return "inserted"


def _import_user_group(cur, row):
    group_id = _clean(row.get("id_possition"))
    name = _clean(row.get("name_possition"))
    description = _clean(row.get("description"))

    if group_id:
        cur.execute(
            """
            SELECT id_possition, name_possition, description
            FROM user_material_groups
            WHERE btrim(id_possition) = btrim(%s)
            LIMIT 1
            """,
            (group_id,),
        )
        same_id = cur.fetchone()
        if same_id:
            raise ValueError("Группа с таким ID уже есть в справочнике." + _format_existing_matches([same_id]))

    cur.execute(
        """
        SELECT id_possition, name_possition, description
        FROM user_material_groups
        WHERE lower(btrim(name_possition)) = lower(btrim(%s))
        ORDER BY id_possition
        """,
        (name,),
    )
    exact_matches = cur.fetchall()
    if exact_matches:
        raise ValueError("Группа с таким наименованием уже есть в справочнике." + _format_existing_matches(exact_matches))

    similar_matches = _fetch_user_group_similar_matches(cur, name)
    if similar_matches:
        raise ValueError(
            "В справочнике уже есть похожие группы. Проверьте, точно ли нужно добавлять новую."
            + _format_existing_matches(similar_matches)
        )

    group_id = group_id or _next_masked_id(cur, "user_material_groups", "id_possition", "C", 3)
    cur.execute(
        """
        INSERT INTO user_material_groups (id_possition, name_possition, description)
        VALUES (%s,%s,%s)
        """,
        (group_id, name, description),
    )
    return "inserted"


def _import_supplier(cur, row):
    ensure_supplier_id_schema(cur)
    inn = _clean(row.get("inn"))
    name = _clean(row.get("name"))

    if not inn or len(str(inn)) not in (10, 12) or not str(inn).isdigit():
        raise ValueError("ИНН поставщика должен состоять из 10 или 12 цифр.")

    cur.execute(
        """
        SELECT supplier_id, inn, name
        FROM suppliers
        WHERE btrim(inn) = btrim(%s)
        LIMIT 1
        """,
        (inn,),
    )
    same_inn = cur.fetchone()
    if same_inn:
        raise ValueError("Поставщик с таким ИНН уже есть в справочнике." + _format_existing_matches([same_inn]))

    optional_values = {
        "short_name": _clean(row.get("short_name")),
        "registration_number": _clean(row.get("registration_number")),
        "registration_date": _clean(row.get("registration_date")),
        "address": _clean(row.get("address")),
        "management": _clean(row.get("management")),
        "management_position": _clean(row.get("management_position")),
        "okved2_code": resolve_okved2_code(cur, row.get("okved2_code"), strict=True),
        "organizational_legal_form": _clean(row.get("organizational_legal_form")),
        "ownership_form": _clean(row.get("ownership_form")),
        "company_size": _clean(row.get("company_size")),
        "phone": _clean(row.get("phone")),
        "email": _clean(row.get("email")),
        "website": _clean(row.get("website")),
        "tax_regime": _clean(row.get("tax_regime")),
    }

    cur.execute(
        """
        INSERT INTO suppliers (
            supplier_id, inn, name, short_name, registration_number, registration_date,
            address, management, management_position, okved2_code, organizational_legal_form,
            ownership_form, company_size, phone, email, website, tax_regime
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING supplier_id
        """,
        (
            next_supplier_id(cur), inn, name, optional_values["short_name"],
            optional_values["registration_number"], optional_values["registration_date"],
            optional_values["address"], optional_values["management"],
            optional_values["management_position"], optional_values["okved2_code"],
            optional_values["organizational_legal_form"], optional_values["ownership_form"],
            optional_values["company_size"], optional_values["phone"], optional_values["email"],
            optional_values["website"], optional_values["tax_regime"],
        ),
    )
    supplier_id = cur.fetchone()["supplier_id"]

    report_year = _as_int(row.get("report_year"))
    if report_year:
        cur.execute(
            """
            INSERT INTO supplier_financials (
                supplier_id, report_year, average_headcount, credit_limit_rub,
                pending_claims_as_defendant_rub, enforcement_proceedings_rub, charter_capital_rub,
                income_rub, expenses_rub, taxes_rub, total_assets_rub,
                retained_earnings_uncovered_loss_rub, capital_and_reserves_rub,
                long_term_liabilities_rub, short_term_liabilities_rub, revenue_rub,
                profit_loss_from_sales_rub, net_profit_loss_rub
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (supplier_id, report_year)
            DO UPDATE SET
                average_headcount = COALESCE(EXCLUDED.average_headcount, supplier_financials.average_headcount),
                credit_limit_rub = COALESCE(EXCLUDED.credit_limit_rub, supplier_financials.credit_limit_rub),
                pending_claims_as_defendant_rub = COALESCE(EXCLUDED.pending_claims_as_defendant_rub, supplier_financials.pending_claims_as_defendant_rub),
                enforcement_proceedings_rub = COALESCE(EXCLUDED.enforcement_proceedings_rub, supplier_financials.enforcement_proceedings_rub),
                charter_capital_rub = COALESCE(EXCLUDED.charter_capital_rub, supplier_financials.charter_capital_rub),
                income_rub = COALESCE(EXCLUDED.income_rub, supplier_financials.income_rub),
                expenses_rub = COALESCE(EXCLUDED.expenses_rub, supplier_financials.expenses_rub),
                taxes_rub = COALESCE(EXCLUDED.taxes_rub, supplier_financials.taxes_rub),
                total_assets_rub = COALESCE(EXCLUDED.total_assets_rub, supplier_financials.total_assets_rub),
                retained_earnings_uncovered_loss_rub = COALESCE(EXCLUDED.retained_earnings_uncovered_loss_rub, supplier_financials.retained_earnings_uncovered_loss_rub),
                capital_and_reserves_rub = COALESCE(EXCLUDED.capital_and_reserves_rub, supplier_financials.capital_and_reserves_rub),
                long_term_liabilities_rub = COALESCE(EXCLUDED.long_term_liabilities_rub, supplier_financials.long_term_liabilities_rub),
                short_term_liabilities_rub = COALESCE(EXCLUDED.short_term_liabilities_rub, supplier_financials.short_term_liabilities_rub),
                revenue_rub = COALESCE(EXCLUDED.revenue_rub, supplier_financials.revenue_rub),
                profit_loss_from_sales_rub = COALESCE(EXCLUDED.profit_loss_from_sales_rub, supplier_financials.profit_loss_from_sales_rub),
                net_profit_loss_rub = COALESCE(EXCLUDED.net_profit_loss_rub, supplier_financials.net_profit_loss_rub),
                updated_at = now()
            """,
            (
                supplier_id, report_year, _as_int(row.get("average_headcount")),
                _as_float(row.get("credit_limit_rub")), _as_float(row.get("pending_claims_as_defendant_rub")),
                _as_float(row.get("enforcement_proceedings_rub")), _as_float(row.get("charter_capital_rub")),
                _as_float(row.get("income_rub")), _as_float(row.get("expenses_rub")),
                _as_float(row.get("taxes_rub")), _as_float(row.get("total_assets_rub")),
                _as_float(row.get("retained_earnings_uncovered_loss_rub")),
                _as_float(row.get("capital_and_reserves_rub")), _as_float(row.get("long_term_liabilities_rub")),
                _as_float(row.get("short_term_liabilities_rub")), _as_float(row.get("revenue_rub")),
                _as_float(row.get("profit_loss_from_sales_rub")), _as_float(row.get("net_profit_loss_rub")),
            ),
        )

    return "inserted"


IMPORT_HANDLERS = {
    "materials": _import_material,
    "okpd2": _import_okpd2,
    "okved2": _import_okved2,
    "user-groups": _import_user_group,
    "units": _import_unit,
    "work-doc-subjects": _import_work_doc_subject,
    "suppliers": _import_supplier,
}


def import_dictionary_rows(cur, dictionary_type: str, rows: List[dict]):
    fields = get_dictionary_import_fields(dictionary_type)
    handler = IMPORT_HANDLERS[dictionary_type]

    result = {
        "status": "OK",
        "dictionary_type": dictionary_type,
        "total_rows": len(rows),
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "errors": [],
    }

    for row in rows:
        row_no = row.get("__source_row_no")

        missed = _validate_required(row, fields)

        if missed:
            result["skipped_count"] += 1
            result["errors"].append({
                "row": row_no,
                "error": f"Не заполнены обязательные поля: {', '.join(missed)}",
            })
            continue

        try:
            action = handler(cur, row)

            if action == "inserted":
                result["inserted_count"] += 1
            elif action == "updated":
                result["updated_count"] += 1
            else:
                result["skipped_count"] += 1

        except Exception as error:
            result["skipped_count"] += 1
            result["errors"].append({
                "row": row_no,
                "error": str(error),
            })

    if result["errors"]:
        result["status"] = "PARTIAL_OK"

    return result
