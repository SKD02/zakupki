from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.runtime_settings import get_settings_payload, infer_smtp_preset, save_smtp_settings

router = APIRouter()


class SmtpSettingsPayload(BaseModel):
    username: str = ""
    password: Optional[str] = None
    from_email: Optional[str] = None
    from_name: str = "Отдел закупок"
    host: Optional[str] = None
    port: Optional[int] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    timeout: int = Field(default=30, ge=1, le=300)
    auto_provider: bool = True


@router.get("")
def get_settings():
    return get_settings_payload()


@router.get("/smtp-preset")
def get_smtp_preset(email: str = ""):
    return infer_smtp_preset(email)


@router.post("/smtp")
def update_smtp_settings(payload: SmtpSettingsPayload):
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return save_smtp_settings(data)
