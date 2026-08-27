"""异步 SQLAlchemy 引擎、会话工厂与数据库依赖。"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# 1. 创建异步数据库引擎
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,  # 拿连接前 ping 一下数据库，剔除失效连接，防止断连报错
    pool_recycle=1800,   # 连接存活 30 分钟后强制回收，避免 MySQL 长时间空闲断开
    pool_size=10,        # 连接池常驻最大连接数
    max_overflow=20,     # 忙时最多额外扩容的临时连接数
    echo=False,
)

# 2. 创建会话工厂，用来生成数据库会话对象
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 之后不使对象过期，提交完仍可读取模型属性
)


# 3. FastAPI 依赖函数：路由里 Depends(get_db) 使用
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """为单次请求提供自动关闭的异步数据库会话。"""

    async with SessionLocal() as session:
        yield session


# 4. 数据库连通性检查
async def check_database() -> None:
    """执行轻量查询，验证数据库连接是否可用。"""

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("数据库连接成功")
