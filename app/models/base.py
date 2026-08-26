"""
模型基类模块。

所有 ORM 模型统一继承 Base（SQLAlchemy 声明式基类），
框架根据继承 Base 的类自动收集元数据，用于建表与迁移。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """声明式基类：所有业务模型的父类，负责注册模型元数据（MetaData）。"""
    pass
