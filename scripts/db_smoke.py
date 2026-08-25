import sys
from pathlib import Path
# 把项目根目录加入python搜索路径
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import text
from app.core.database import SessionLocal, check_database

async def main():
    await check_database()
    print("SELECT 1: OK")

    async with SessionLocal() as db:
        users = await db.scalar(text("SELECT COUNT(*) FROM users"))
        images = await db.scalar(text("SELECT COUNT(*) FROM images"))
        print(f"users={users}, images={images}")

if __name__ == "__main__":
    asyncio.run(main())
