"""数据库 Engine 与会话生命周期管理，仅向 API 和 Worker 提供短事务会话。"""

from collections.abc import AsyncGenerator, Generator
from functools import lru_cache

from sqlalchemy import Boolean, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy.orm import sessionmaker, with_loader_criteria
from sqlmodel import Field, Session, SQLModel

from app.core.config import get_settings


class SQLModelBase(SQLModel):
    """全部 SQLModel 领域实体共用的声明式基类。

    该基类提供统一元数据入口与逻辑删除标记，具体表、关系与业务约束必须由各领域模型声明。
    """

    is_del: bool = Field(
        default=False,
        nullable=False,
        sa_type=Boolean,
        sa_column_kwargs={"server_default": "false", "comment": "业务记录逻辑删除标记，true 表示常规查询不可见"},
    )


@event.listens_for(SQLAlchemySession, "do_orm_execute")
def _filter_soft_deleted_records(execute_state) -> None:
    """为 ORM 常规查询自动排除逻辑删除记录，审计查询可显式传入 include_deleted 执行选项。"""

    if not execute_state.is_select or execute_state.execution_options.get("include_deleted"):
        return
    for mapper in SQLModelBase._sa_registry.mappers:
        if "is_del" in mapper.columns:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(mapper.class_, lambda model: model.is_del.is_(False), include_aliases=True)
            )


@lru_cache
def get_engine() -> Engine:
    """创建进程内唯一的连接池 Engine，连接失效时由 SQLAlchemy 在借出前探测。"""

    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """创建复用共享 Engine 的会话工厂，调用方负责界定并提交业务事务。"""

    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


@lru_cache
def get_async_engine() -> AsyncEngine:
    settings = get_settings()
    async_database_url = settings.database_async_url
    if async_database_url is None:
        async_database_url = make_url(settings.database_url).set(drivername="postgresql+asyncpg")
    return create_async_engine(
        async_database_url,
        pool_pre_ping=True,
        pool_size=settings.database_async_pool_size,
        max_overflow=settings.database_async_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
    )


@lru_cache
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_async_engine(),
        sync_session_class=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """为单个 HTTP 请求提供会话，并在请求结束后保证关闭连接。"""

    with get_session_factory()() as session:
        yield session


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session_factory()() as session:
        yield session


def dispose_database() -> None:
    """释放当前进程的数据库连接池，供 API 关闭和 Worker 进程退出时调用。"""

    get_engine().dispose()


async def dispose_async_database() -> None:
    if get_async_engine.cache_info().currsize:
        await get_async_engine().dispose()
    get_async_session_factory.cache_clear()
    get_async_engine.cache_clear()
