import re
from urllib.parse import urlsplit
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    keitaro_url: str = "https://example.invalid"
    keitaro_api_key: str = ""
    database_url: str = "sqlite:///./wrapper.db"
    campaign_prefix: str = "test_pokotilo_"
    app_user: str = "admin"
    app_password: str = ""
    demo_mode: bool = False
    @field_validator("keitaro_url")
    @classmethod
    def tracker_url(cls, value):
        parsed = urlsplit(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("KEITARO_URL: укажите http(s) адрес трекера без логина и пароля")
        if parsed.path.rstrip("/") not in ("", "/admin") or parsed.query or parsed.fragment:
            raise ValueError("KEITARO_URL: нужен корневой адрес трекера без параметров")
        return f"{parsed.scheme}://{parsed.netloc}"

    @field_validator("campaign_prefix")
    @classmethod
    def test_prefix(cls, value):
        if not re.fullmatch(r"test_[\w-]+_", value):
            raise ValueError("CAMPAIGN_PREFIX: используйте test_фамилия_")
        return value

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
