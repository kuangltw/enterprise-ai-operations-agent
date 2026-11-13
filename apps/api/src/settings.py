"""執行環境設定。禁止在程式碼中寫死真實密鑰。"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """由環境載入服務設定；缺少 M2 儲存憑證時上傳功能保持關閉。"""
    database_url: str
    erp_base_url: str = "http://demo-erp:8080"
    jwt_signing_key: str | None = None
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str | None = None
    minio_secure: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
