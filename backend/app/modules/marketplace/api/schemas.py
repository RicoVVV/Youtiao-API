from uuid import UUID

from pydantic import BaseModel, Field


class ModelMarketplaceListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    model_type: str | None = Field(default=None, min_length=1, max_length=32)
    keyword: str | None = Field(default=None, min_length=1, max_length=128)


class ModelMarketplaceDetailQuery(BaseModel):
    model_id: UUID
