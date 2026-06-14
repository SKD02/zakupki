import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "zakupki")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")

    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mail.ru")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "sidorov_kirya@bk.ru")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "9eJzuBHh5bhKqMmaLx7N")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Отдел закупок")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() in ("1", "true", "yes", "on")
    SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes", "on")
    SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "30"))

settings = Settings()
