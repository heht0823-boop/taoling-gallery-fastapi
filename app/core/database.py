from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# 1. 创建异步数据库引擎
engine=create_async_engine(
    settings.database_url,   # 从配置读取数据库连接url(mysql+asyncmy://xxx)
    pool_pre_ping=True,      # 拿连接前ping一下数据库，剔除失效连接，防止断连报错
    pool_recycle=1800,       # 连接存活30分钟后强制回收，避免MySQL长时间空闲断开
    pool_size=10,            # 连接池常驻最大连接数10
    max_overflow=20,         # 忙的时候最多额外扩容20个临时连接
    echo=False               # 关闭SQL打印日志，开发可以改成True看执行sql
)

# 2. 创建会话工厂，用来生成数据库会话对象
SessionLocal = async_sessionmaker(
    bind=engine,                # 绑定上面的引擎
    class_=AsyncSession,        # 使用异步会话
    expire_on_commit=False,     # commit之后不把对象过期，提交完还可以读取模型属性，FastAPI常用
)

# 3. FastAPI依赖函数：获取数据库会话，路由里Depends(get_db)使用
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session: # 创建会话，退出自动close释放连接还给连接池
        yield session                    # 把session交给接口使用，接口结束自动清理资源

# 4. 数据库连通性测试函数
async def check_database() -> None:
    async with engine.connect() as conn: # 获取一条数据库连接
        await conn.execute(text("SELECT 1"))
        # 执行一条简单SQL，验证账号、地址、网络通不通
        print("数据库连接成功!") # 打印检查完成
