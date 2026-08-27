from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.user import User


async def test_read_one_user():
    async with SessionLocal() as db:
        result=await db.execute(
            select(User)
            .where(User.deleted_at.is_(None))
            .limit(1)
        )
        user=result.scalar_one_or_none()
        assert user is None or isinstance(user.username,str)