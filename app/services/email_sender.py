import re
import smtplib
from email.message import EmailMessage
from typing import Iterable, List, Optional, Tuple
from email.utils import formataddr
from app.config import settings
from app.services.runtime_settings import get_effective_smtp_settings

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def extract_emails(value: Optional[str]) -> List[str]:
    if not value:
        return []
    seen = set()
    result = []
    for email in EMAIL_RE.findall(value):
        normalized = email.strip()
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def build_procurement_email(batch: dict, items: Iterable[dict]) -> Tuple[str, str]:
    supplier_name = batch.get("supplier_name") or "поставщик"
    application_id = batch.get("application_id")
    kp_request_code = batch.get("kp_request_code") or batch.get("request_code")
    request_label = kp_request_code or f"заявке #{application_id}"

    period = ""
    if batch.get("supply_start_date") or batch.get("supply_end_date"):
        period = f"Период поставки: {batch.get('supply_start_date') or '—'} — {batch.get('supply_end_date') or '—'}\n"

    lines = [
        f"Добрый день, {supplier_name}!",
        "",
        "Просим рассмотреть возможность поставки материалов по запросу КП.",
        f"Запрос КП: {request_label}",
        period.rstrip(),
        "",
        "Позиции:",
    ]

    def aggregate_items(items):
        grouped = {}

        for item in items:
            key = (
                item.get("material_id") or "",
                item.get("material_name") or "",
                item.get("unit") or "",
            )

            if key not in grouped:
                grouped[key] = {
                    **item,
                    "quantity": 0,
                    "work_doc_codes": set(),
                    "comments": set(),
                }

            try:
                grouped[key]["quantity"] += float(item.get("quantity") or 0)
            except Exception:
                pass

            if item.get("work_doc_code"):
                grouped[key]["work_doc_codes"].add(str(item.get("work_doc_code")))

            if item.get("characteristics_comment"):
                grouped[key]["comments"].add(str(item.get("characteristics_comment")))

        result = []

        for item in grouped.values():
            item["work_doc_code"] = ", ".join(sorted(item["work_doc_codes"])) or "—"
            item["characteristics_comment"] = "; ".join(sorted(item["comments"]))
            result.append(item)

        return result

    for index, item in enumerate(aggregate_items(items), start=1):
        material = item.get("material_name") or "Материал"
        qty = item.get("quantity") or ""
        unit = item.get("unit") or ""
        start = item.get("supply_start_date") or "—"
        end = item.get("supply_end_date") or "—"
        comment = item.get("characteristics_comment") or ""
        line = f"{index}. {material} — {qty} {unit}; срок: {start} — {end}"
        if comment:
            line += f"; характеристики: {comment}"
        lines.append(line)

    lines.extend([
        "",
        "Просим направить коммерческое предложение с указанием цены, сроков поставки и условий оплаты.",
        "",
        "С уважением,",
        "Отдел закупок",
    ])

    subject = f"Запрос КП {request_label}"
    if batch.get("user_group_id"):
        subject += f" / {batch.get('user_group_id')}"

    return subject, "\n".join(line for line in lines if line is not None)


def send_email_smtp(to_emails: List[str], subject: str, body: str) -> None:
    smtp_settings = get_effective_smtp_settings()
    if not smtp_settings.host:
        raise RuntimeError("SMTP_HOST не задан. Заполните настройки почты в панели настроек или в .env")
    if not to_emails:
        raise RuntimeError("Не найден email получателя")

    msg = EmailMessage()
    msg["Subject"] = subject

    from_email = smtp_settings.from_email or smtp_settings.username or "no-reply@example.local"
    if smtp_settings.from_name:
        msg["From"] = formataddr((smtp_settings.from_name, from_email))
    else:
        msg["From"] = from_email

    msg["To"] = ", ".join(to_emails)
    msg["Bcc"] = from_email
    msg.set_content(body)

    if smtp_settings.use_ssl:
        with smtplib.SMTP_SSL(smtp_settings.host, smtp_settings.port, timeout=smtp_settings.timeout) as smtp:
            _login_if_needed(smtp, smtp_settings)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(smtp_settings.host, smtp_settings.port, timeout=smtp_settings.timeout) as smtp:
            if smtp_settings.use_tls:
                smtp.starttls()
            _login_if_needed(smtp, smtp_settings)
            smtp.send_message(msg)


def _login_if_needed(smtp, smtp_settings) -> None:
    if smtp_settings.username:
        smtp.login(smtp_settings.username, smtp_settings.password or "")
