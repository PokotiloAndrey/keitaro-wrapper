from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    keitaro_url: str = "https://example.invalid"
    keitaro_api_key: str = ""
    database_url: str = "sqlite:///./wrapper.db"
    campaign_prefix: str = "test_pokotilo_"
    app_user: str = "admin"
    app_password: str = ""
    demo_mode: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
