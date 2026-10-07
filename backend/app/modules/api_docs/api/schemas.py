"""接口文档 HTTP DTO。

目录与详情直接返回应用层组装的展示结构，因此这里只定义查询参数的基础校验。
"""

from pydantic import BaseModel, Field


class ApiDocsListQuery(BaseModel):
    model_type: str | None = Field(default=None, min_length=1, max_length=32)


class ApiDocsDetailQuery(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
