"""
模型包统一出口。

集中导入并暴露全部 ORM 模型类：
- 业务代码只需 `from app.models import User` 即可引用；
- import 即完成所有模型的注册，供 create_all / Alembic 扫描建表。
"""
from app.models.admin_log import AdminLog  # 管理员操作日志表
from app.models.ai import AiConversation, AiMemory, AiMessage  # AI 对话、记忆、消息表
from app.models.base import Base  # 模型声明式基类
from app.models.behavior import DownloadRecord, Favorite, ImageViewRecord  # 下载、收藏、浏览记录表
from app.models.image import Category, Image, ImageTag, Tag  # 分类、图片、图片标签关联、标签表
from app.models.message import UserMessage  # 用户留言表
from app.models.user import User, UserStat  # 用户表、用户统计表
from app.models.weather import WeatherForecastCache, WeatherLiveCache  # 天气预报、实时天气缓存表

__all__ = [
    "AdminLog",
    "AiConversation",
    "AiMemory",
    "AiMessage",
    "Base",
    "Category",
    "DownloadRecord",
    "Favorite",
    "Image",
    "ImageTag",
    "ImageViewRecord",
    "Tag",
    "User",
    "UserMessage",
    "UserStat",
    "WeatherForecastCache",
    "WeatherLiveCache",
]
