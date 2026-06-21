from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.config import settings as env_settings
from app.database import get_connection

SETTING_KEYS = {
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL",
    "SMTP_FROM_NAME",
    "SMTP_USE_TLS",
    "SMTP_USE_SSL",
    "SMTP_TIMEOUT",
}

PROVIDER_PRESETS = {
    "mail.ru": {"host": "smtp.mail.ru", "port": 465, "use_ssl": True, "use_tls": False},
    "bk.ru": {"host": "smtp.mail.ru", "port": 465, "use_ssl": True, "use_tls": False},
    "inbox.ru": {"host": "smtp.mail.ru", "port": 465, "use_ssl": True, "use_tls": False},
    "list.ru": {"host": "smtp.mail.ru", "port": 465, "use_ssl": True, "use_tls": False},
    "gmail.com": {"host": "smtp.gmail.com", "port": 465, "use_ssl": True, "use_tls": False},
    "googlemail.com": {"host": "smtp.gmail.com", "port": 465, "use_ssl": True, "use_tls": False},
    "yandex.ru": {"host": "smtp.yandex.ru", "port": 465, "use_ssl": True, "use_tls": False},
    "ya.ru": {"host": "smtp.yandex.ru", "port": 465, "use_ssl": True, "use_tls": False},
    "yandex.com": {"host": "smtp.yandex.com", "port": 465, "use_ssl": True, "use_tls": False},
    "outlook.com": {"host": "smtp.office365.com", "port": 587, "use_ssl": False, "use_tls": True},
    "hotmail.com": {"host": "smtp.office365.com", "port": 587, "use_ssl": False, "use_tls": True},
    "live.com": {"host": "smtp.office365.com", "port": 587, "use_ssl": False, "use_tls": True},
    "rambler.ru": {"host": "smtp.rambler.ru", "port": 465, "use_ssl": True, "use_tls": False},
}


def _bool_to_text(value: bool) -> str:
    return "true" if bool(value) else "false"


def _text_to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def mask_secret(value: Optional[str]) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


def infer_smtp_preset(email: Optional[str]) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    domain = email.split("@")[-1] if "@" in email else email
    preset = PROVIDER_PRESETS.get(domain)
    if preset:
        return {"provider": domain, **preset}
    return {"provider": "custom", "host": "", "port": 465, "use_ssl": True, "use_tls": False}


@dataclass
class EffectiveSmtpSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    from_name: str
    use_tls: bool
    use_ssl: bool
    timeout: int


def ensure_settings_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key text PRIMARY KEY,
            value text NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def get_db_settings(cur) -> Dict[str, str]:
    ensure_settings_table(cur)
    cur.execute(
        "SELECT key, value FROM app_settings WHERE key = ANY(%s)",
        (list(SETTING_KEYS),),
    )
    return {row["key"]: row["value"] for row in cur.fetchall()}


def set_db_settings(cur, values: Dict[str, Any]) -> None:
    ensure_settings_table(cur)
    for key, value in values.items():
        if key not in SETTING_KEYS:
            continue
        cur.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
            """,
            (key, None if value is None else str(value)),
        )


def build_effective_smtp_settings(db_values: Optional[Dict[str, str]] = None) -> EffectiveSmtpSettings:
    values = db_values or {}
    username = values.get("SMTP_USERNAME") or env_settings.SMTP_USERNAME or ""
    from_email = values.get("SMTP_FROM_EMAIL") or env_settings.SMTP_FROM_EMAIL or username
    return EffectiveSmtpSettings(
        host=values.get("SMTP_HOST") or env_settings.SMTP_HOST or "",
        port=_to_int(values.get("SMTP_PORT"), env_settings.SMTP_PORT),
        username=username,
        password=values.get("SMTP_PASSWORD") or env_settings.SMTP_PASSWORD or "",
        from_email=from_email,
        from_name=values.get("SMTP_FROM_NAME") or env_settings.SMTP_FROM_NAME or "Отдел закупок",
        use_tls=_text_to_bool(values.get("SMTP_USE_TLS"), env_settings.SMTP_USE_TLS),
        use_ssl=_text_to_bool(values.get("SMTP_USE_SSL"), env_settings.SMTP_USE_SSL),
        timeout=_to_int(values.get("SMTP_TIMEOUT"), env_settings.SMTP_TIMEOUT),
    )


def get_effective_smtp_settings() -> EffectiveSmtpSettings:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                db_values = get_db_settings(cur)
                return build_effective_smtp_settings(db_values)
    except Exception:
        return build_effective_smtp_settings({})


def get_settings_payload() -> Dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            db_values = get_db_settings(cur)
    smtp = build_effective_smtp_settings(db_values)
    preset = infer_smtp_preset(smtp.username or smtp.from_email)
    return {
        "smtp": {
            "host": smtp.host,
            "port": smtp.port,
            "username": smtp.username,
            "password_mask": mask_secret(smtp.password),
            "password_set": bool(smtp.password),
            "from_email": smtp.from_email,
            "from_name": smtp.from_name,
            "use_tls": smtp.use_tls,
            "use_ssl": smtp.use_ssl,
            "timeout": smtp.timeout,
            "provider": preset.get("provider"),
        },
        "runtime": {
            "app_host": env_settings.APP_HOST,
            "app_port": env_settings.APP_PORT,
            "db_host": env_settings.DB_HOST,
            "db_port": env_settings.DB_PORT,
            "db_name": env_settings.DB_NAME,
            "db_user": env_settings.DB_USER,
            "cors_origins": env_settings.CORS_ORIGINS,
        },
    }


def save_smtp_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = (payload.get("username") or payload.get("smtp_username") or "").strip()
    from_email = (payload.get("from_email") or payload.get("smtp_from_email") or username).strip()
    password = payload.get("password")
    auto_provider = bool(payload.get("auto_provider", True))

    if auto_provider:
        preset = infer_smtp_preset(username or from_email)
        host = payload.get("host") or preset.get("host") or ""
        port = payload.get("port") or preset.get("port") or 465
        use_ssl = payload.get("use_ssl") if payload.get("use_ssl") is not None else preset.get("use_ssl", True)
        use_tls = payload.get("use_tls") if payload.get("use_tls") is not None else preset.get("use_tls", False)
    else:
        host = payload.get("host") or ""
        port = payload.get("port") or 465
        use_ssl = payload.get("use_ssl", True)
        use_tls = payload.get("use_tls", False)

    values = {
        "SMTP_HOST": host,
        "SMTP_PORT": _to_int(port, 465),
        "SMTP_USERNAME": username,
        "SMTP_FROM_EMAIL": from_email or username,
        "SMTP_FROM_NAME": payload.get("from_name") or "Отдел закупок",
        "SMTP_USE_TLS": _bool_to_text(bool(use_tls)),
        "SMTP_USE_SSL": _bool_to_text(bool(use_ssl)),
        "SMTP_TIMEOUT": _to_int(payload.get("timeout"), 30),
    }
    if password:
        values["SMTP_PASSWORD"] = password

    with get_connection() as conn:
        with conn.cursor() as cur:
            set_db_settings(cur, values)
        conn.commit()
    return get_settings_payload()
