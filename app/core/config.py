from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置，字段名大写后自动对应 .env 中的同名环境变量。

    例如 `app_env` 自动读取 `APP_ENV`，无需手写 alias。
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- 应用基础环境配置 -----
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_url: str = "http://127.0.0.1:8000"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ----- MySQL 数据库配置 -----
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "taoling_gallery"
    db_user: str = "root"
    db_password: str = ""

    # ----- JWT 登录鉴权 & Cookie 配置 -----
    jwt_secret: str = "debug_secret_123456"
    jwt_expires_in: str = "7d"
    auth_cookie_name: str = "taoling_auth"
    auth_cookie_samesite: str = "lax"
    auth_cookie_secure: bool = False
    auth_cookie_domain: str | None = None
    auth_cookie_max_age: str = "7d"

    # ----- 文件上传 & 图片处理配置 -----
    upload_root: str = "./uploads"
    upload_max_size_mb: int = 20
    image_optimizer_format: str = "webp"
    image_optimizer_quality: int = 78
    image_thumbnail_width: int = 420
    image_optimizer_query_template: str = ""
    image_optimizer_url_template: str = ""

    # ----- 阿里云内容安全（UGC 审核） -----
    content_security_enabled: bool = False
    ali_access_key_id: str = ""
    ali_access_key_secret: str = ""
    ali_region_id: str = "cn-shanghai"
    ali_text_action: str = "TextModerationPlus"
    ali_service_name: str = "ugc_moderation_byllm_pro"
    ali_endpoint: str = "green-cip.cn-shanghai.aliyuncs.com"
    ali_api_version: str = "2022-03-02"
    ali_timeout_ms: int = 15000

    # ----- 高德地图天气接口配置 -----
    amap_key: str = ""
    amap_live_cache_minutes: int = 30
    amap_forecast_cache_minutes: int = 360

    # ----- 阿里云通义千问 DashScope AI 大模型 -----
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"
    ai_timeout_ms: int = 30000

    # ----- 系统初始化管理员账号 -----
    admin_username: str = "hetao"
    admin_email: str = "admin@taoling.local"
    admin_password: str = ""

    @property
    def database_url(self) -> URL:
        """SQLAlchemy 异步连接 URL，优先使用环境变量覆盖数据库配置。"""
        return URL.create(
            drivername="mysql+asyncmy",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def cors_origin_list(self) -> list[str]:
        """解析 CORS 允许的跨域来源：将逗号分隔的字符串拆成列表，自动去除空项与首尾空格。"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def upload_path(self) -> Path:
        """上传文件根目录的绝对路径：配置为绝对路径则直接用，相对路径基于项目根目录拼接。"""
        path = Path(self.upload_root)
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    """带缓存的配置获取函数：进程内只加载一次 .env，后续复用同一实例。"""
    return Settings()


settings = get_settings()
