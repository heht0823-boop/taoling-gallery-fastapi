from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_log import AdminLog
from app.models.user import User


async def write_log(
    db: AsyncSession,
    *,
    actor: User | None,
    action_type: str,
    target_type: str | None,
    target_id: int | None,
    title: str,
    content: str | None = None,
    ip_address: str | None = None,
) -> None:
    """
    写入管理员操作日志，往数据库新增一条 AdminLog 记录
    不会自动commit！调用方需要手动 await db.commit()
    :param db: 数据库会话对象
    :param actor: 操作人用户对象，可以为 None（系统自动操作，无真实用户）
    :param action_type: 操作类型字符串，例如："user_create"、"user_delete"
    :param target_type: 操作目标对象类型，例如："user"、"article"
    :param target_id: 操作目标数据ID
    :param title: 日志简短标题
    :param content: 日志详细描述内容，可选
    :param ip_address: 操作者IP地址，可选
    """
    # 将日志模型加入数据库会话，只是加入待处理队列，还没真正提交到数据库
    db.add(
        AdminLog(
            # 操作人ID，如果actor为None（系统操作）则存null
            actor_id=actor.id if actor else None,
            # 操作人用户名，无用户时填 system
            actor_name=actor.username if actor else "system",
            # 操作人角色，无用户时填 system
            actor_role=actor.role if actor else "system",
            # 操作类型标记
            action_type=action_type,
            # 被操作的数据类型
            target_type=target_type,
            # 被操作数据的主键ID
            target_id=target_id,
            # 日志标题
            title=title,
            # 日志详情文本
            content=content,
            # 请求客户端IP
            ip_address=ip_address,
        )
    )
