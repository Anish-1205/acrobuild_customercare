"""Administrator-only integration configuration."""
import sqlite3
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, SecretStr, field_validator

from api_context import require_admin_user
from services.acrobuild_company_service import _cs_api_defaults, _cs_api_config
from services.cs_api_settings_service import save_cs_api_settings

router = APIRouter(prefix="/api/admin/cs-api-settings", dependencies=[Depends(require_admin_user)])


class CSApiSettingsRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr = SecretStr("")
    company_id: int = Field(gt=0, strict=True)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value):
        value = value.strip().rstrip("/")
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise ValueError("Enter a valid HTTP or HTTPS base URL.") from None
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or any(character.isspace() for character in value)):
            raise ValueError("Enter an HTTP or HTTPS URL without credentials, query, or fragment.")
        return value


@router.get("")
def get_settings(response: Response):
    response.headers["Cache-Control"] = "no-store"
    config = _cs_api_config()
    return {"base_url": config["base_url"], "company_id": config["company_id"],
            "api_key_configured": bool(config["api_key"])}


@router.put("")
def update_settings(payload: CSApiSettingsRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    key = payload.api_key.get_secret_value().strip()
    if len(key) > 4096 or any(ord(character) < 32 or ord(character) > 126 for character in key):
        raise HTTPException(422, "API key must contain printable ASCII characters only (maximum 4096).")
    try:
        return save_cs_api_settings(payload.base_url, key, payload.company_id, _cs_api_defaults())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(500, "Could not save CS API settings.") from error
