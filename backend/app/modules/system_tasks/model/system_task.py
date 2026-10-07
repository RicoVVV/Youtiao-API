import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase


class SystemTaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class SystemTask(SQLModelBase, table=True):
    __tablename__ = "system_tasks"
    __table_args__ = (
        UniqueConstraint("active_key", name="uq_system_tasks_active_key"),
        Index("ix_system_tasks_type_status_created", "task_type", "status", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    task_type: str = Field(sa_column=Column(String(64), nullable=False))
    active_key: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    status: SystemTaskStatus = Field(
        default=SystemTaskStatus.pending,
        sa_column=Column(Enum(SystemTaskStatus, name="system_task_status"), nullable=False),
    )
    runner_id: str | None = Field(default=None, sa_column=Column(String(128)))
    lease_expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    progress: int = Field(default=0)
    result: dict | None = Field(default=None, sa_column=Column(JSONB))
    error: dict | None = Field(default=None, sa_column=Column(JSONB))
