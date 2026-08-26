import sys
from pathlib import Path

# 获取当前脚本文件的上一级目录(项目根目录)，添加到Python模块搜索路径
# 解决直接运行该脚本时，import app.* 模块找不到的问题
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import text
# 导入数据库会话工厂、数据库初始化检测函数
from app.core.database import SessionLocal, check_database


async def main():
    # 执行数据库连通性检测，校验数据库是否可连接、表是否存在
    await check_database()
    print("SELECT 1: OK")

    # 获取异步数据库会话，上下文管理器自动处理会话关闭释放
    async with SessionLocal() as db:
        # 执行原生SQL，查询users表总记录数
        users = await db.scalar(text("SELECT COUNT(*) FROM users"))
        # 执行原生SQL，查询images表总记录数
        images = await db.scalar(text("SELECT COUNT(*) FROM images"))
        # 打印两张表的数据统计
        print(f"users={users}, images={images}")


if __name__ == "__main__":
    # 启动异步事件循环，执行main异步函数
    asyncio.run(main())
