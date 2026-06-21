import os
from dotenv import load_dotenv

load_dotenv()


def get_bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


class Settings:
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))

    DB_HOST = os.getenv("DB_HOST", "")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Отдел закупок")
    SMTP_USE_TLS = get_bool_env("SMTP_USE_TLS", "true")
    SMTP_USE_SSL = get_bool_env("SMTP_USE_SSL", "false")
    SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "30"))

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")


settings = Settings()