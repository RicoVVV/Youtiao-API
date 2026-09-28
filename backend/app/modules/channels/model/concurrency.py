"""视频任务每用户模型并发覆盖与租约的 ORM 映射。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Uuid, func, text
from sqlmodel import Field

from app.core.database import SQLModelBase


class UserModelConcurrencyOverride(SQLModelBase, table=True):
    """保存用户对指定公开模型的可选并发上限覆盖。"""

    __tablename__ = "user_model_concurrency_overrides"
    __table_args__ = (
        CheckConstraint("concurrency_limit BETWEEN 0 AND 10000", name="ck_user_model_concurrency_overrides_limit"),
        Index(
            "uq_user_model_concurrency_overrides_active",
            "user_id",
            "model_id",
            unique=True,
            postgresql_where=text("is_del = false"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    user_id: UUID = Field(sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True))
    model_id: UUID = Field(sa_column=Column(ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, index=True))
    concurrency_limit: int = Field(sa_column=Column(Integer, nullable=False))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))


class UserConcurrencyLease(SQLModelBase, table=True):
    """保存一个生成资源唯一的每用户模型并发占用及其释放时间。

    ``task_id`` 是通用占用标识：视频任务写入任务 ID，同步生成写入生成资源 ID。两种资源不共享
    数据表，因此这里不设外键，避免同步生成必须存在对应视频任务。
    """

    __tablename__ = "user_concurrency_leases"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    task_id: UUID = Field(sa_column=Column(Uuid, unique=True, nullable=False))
    user_id: UUID = Field(sa_column=Column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True))
    model_id: UUID = Field(sa_column=Column(ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, index=True))
    released_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), index=True))
