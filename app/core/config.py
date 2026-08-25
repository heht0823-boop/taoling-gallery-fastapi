from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field("development", alias="APP_ENV")
    app_host: str = Field("127.0.0.1", alias="APP_HOST")
    app_port: int = Field(8000, alias="APP_PORT")
    app_url: str = Field("http://127.0.0.1:8000", alias="APP_URL")
    cors_origins: str = Field("http://localhost:5173", alias="CORS_ORIGINS")

    db_host: str = Field(alias="DB_HOST")
    db_port: int = Field(3306, alias="DB_PORT")
    db_name: str = Field(alias="DB_NAME")
    db_user: str = Field(alias="DB_USER")
    db_password: str = Field("", alias="DB_PASSWORD")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_expires_in: str = Field("7d", alias="JWT_EXPIRES_IN")
    auth_cookie_name: str = Field("taoling_auth", alias="AUTH_COOKIE_NAME")
    auth_cookie_samesite: str = Field("lax", alias="AUTH_COOKIE_SAMESITE")
    auth_cookie_secure: bool = Field(False, alias="AUTH_COOKIE_SECURE")
    auth_cookie_domain: str | None = Field(None, alias="AUTH_COOKIE_DOMAIN")
    auth_cookie_max_age: str = Field("7d", alias="AUTH_COOKIE_MAX_AGE")

    upload_root: str = Field("./uploads", alias="UPLOAD_ROOT")
    upload_max_size_mb: int = Field(20, alias="UPLOAD_MAX_SIZE_MB")
    image_optimizer_format: str = Field("webp", alias="IMAGE_OPTIMIZER_FORMAT")
    image_optimizer_quality: int = Field(78, alias="IMAGE_OPTIMIZER_QUALITY")
    image_thumbnail_width: int = Field(420, alias="IMAGE_THUMBNAIL_WIDTH")
    image_optimizer_query_template: str = Field("", alias="IMAGE_OPTIMIZER_QUERY_TEMPLATE")
    image_optimizer_url_template: str = Field("", alias="IMAGE_OPTIMIZER_URL_TEMPLATE")

    content_security_enabled: bool = Field(False, alias="CONTENT_SECURITY_ENABLED")
    ali_access_key_id: str = Field("", alias="ALI_ACCESS_KEY_ID")
    ali_access_key_secret: str = Field("", alias="ALI_ACCESS_KEY_SECRET")
    ali_region_id: str = Field("cn-shanghai", alias="ALI_REGION_ID")
    ali_text_action: str = Field("TextModerationPlus", alias="ALI_TEXT_ACTION")
    ali_service_name: str = Field("ugc_moderation_byllm_pro", alias="ALI_SERVICE_NAME")
    ali_endpoint: str = Field("green-cip.cn-shanghai.aliyuncs.com", alias="ALI_ENDPOINT")
    ali_api_version: str = Field("2022-03-02", alias="ALI_API_VERSION")
    ali_timeout_ms: int = Field(15000, alias="ALI_TIMEOUT_MS")

    amap_key: str = Field("", alias="AMAP_KEY")
    amap_live_cache_minutes: int = Field(30, alias="AMAP_LIVE_CACHE_MINUTES")
    amap_forecast_cache_minutes: int = Field(360, alias="AMAP_FORECAST_CACHE_MINUTES")

    dashscope_api_key: str = Field("", alias="DASHSCOPE_API_KEY")
    dashscope_base_url: str = Field("https://dashscope.aliyuncs.com/compatible-mode/v1", alias="DASHSCOPE_BASE_URL")
    dashscope_model: str = Field("qwen-plus", alias="DASHSCOPE_MODEL")
    ai_timeout_ms: int = Field(30000, alias="AI_TIMEOUT_MS")

    admin_username: str = Field("hetao", alias="ADMIN_USERNAME")
    admin_email: str = Field("admin@taoling.local", alias="ADMIN_EMAIL")
    admin_password: str = Field("", alias="ADMIN_PASSWORD")

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="mysql+asyncmy", username=self.db_user, password=self.db_password,
            host=self.db_host, port=self.db_port, database=self.db_name
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_root)
        return path if path.is_absolute() else PROJECT_ROOT / path

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

