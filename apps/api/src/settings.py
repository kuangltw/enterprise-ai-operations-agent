"""執行環境設定。禁止在程式碼中寫死真實密鑰。"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    erp_base_url: str = "http://demo-erp:8080"
    jwt_signing_key: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
