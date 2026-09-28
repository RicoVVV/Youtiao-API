"""视频输入素材事实的 ORM 映射。

素材事实记录一次请求中某个素材字段下已归一化并完成可信计量的输入素材；它不保存原始带签名 URL
或上传令牌，只保存受控存储资源标识、内容摘要、大小和实测视频时长，作为报价与审计的稳定依据。
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.core.database import SQLModelBase


class InputMaterialCategory(str, enum.Enum):
    """输入素材类别；音频可透传 Provider 但不参与视频计价。"""

    video = "video"
    image = "image"
    audio = "audio"


_CATEGORIES = ", ".join(f"'{category.value}'" for category in InputMaterialCategory)


class VideoInputMaterial(SQLModelBase, table=True):
    """一次视频请求中单个素材字段下已归一化的素材事实。

    同一请求内按素材字段与提交位置计数，重复 URL 或相同内容仍分别记录；``extras`` 保存脱敏的
    探测元数据，不得写入带签名 URL、上传令牌或 Provider 密钥。
    """

    __tablename__ = "video_input_materials"
    __table_args__ = (
        CheckConstraint(f"category IN ({_CATEGORIES})", name="ck_video_input_materials_category"),
        CheckConstraint("size_bytes >= 0", name="ck_video_input_materials_size_non_negative"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_video_input_materials_duration_non_negative",
        ),
        Index("ix_video_input_materials_task_field", "task_id", "field_name"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    task_id: UUID = Field(
        sa_column=Column(
            ForeignKey("video_tasks.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="素材事实所属任务，与任务在同一事务内写入",
        )
    )
    field_name: str = Field(sa_column=Column(String(128), nullable=False))
    position: int = Field(sa_column=Column(Integer, nullable=False, comment="素材在字段中的提交位置，从 0 开始"))
    category: str = Field(sa_column=Column(String(16), nullable=False))
    resource_id: str = Field(
        sa_column=Column(String(512), nullable=False, comment="受控存储资源标识，不包含带签名 URL 或上传令牌")
    )
    content_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    size_bytes: int = Field(sa_column=Column(BigInteger, nullable=False))
    duration_seconds: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 6), nullable=True))
    extras: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
