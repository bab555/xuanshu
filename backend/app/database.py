"""
数据库连接与会话管理
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import settings

# 确保数据目录存在
os.makedirs(os.path.dirname(settings.database_url.replace("sqlite+aiosqlite:///", "")), exist_ok=True)

# 创建异步引擎
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# 声明基类
Base = declarative_base()


async def get_db() -> AsyncSession:
    """获取数据库会话（依赖注入用）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库（创建所有表）"""
    # 关键：必须先导入所有模型，确保它们都已注册到 Base.metadata，
    # 否则 create_all 可能只建出部分表（导致用户/抄送/工作流等无法落库映射）。
    from app import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：SQLite 仅 create_all 不会新增列，这里补齐关键软删除列
        if str(settings.database_url).startswith("sqlite"):
            await _sqlite_migrate(conn)


async def _sqlite_migrate(conn):
    """SQLite 轻量迁移：按需新增列（避免线上/本地旧库缺列导致运行时报错）"""
    async def _has_column(table: str, col: str) -> bool:
        rows = await conn.exec_driver_sql(f"PRAGMA table_info({table});")
        cols = [r[1] for r in rows.fetchall()]
        return col in cols

    async def _add_column(table: str, col_def_sql: str):
        await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col_def_sql};")

    # documents.owner_deleted_at
    if await _has_column("documents", "owner_deleted_at") is False:
        await _add_column("documents", "owner_deleted_at DATETIME")

    # document_shares.deleted_at
    if await _has_column("document_shares", "deleted_at") is False:
        await _add_column("document_shares", "deleted_at DATETIME")

