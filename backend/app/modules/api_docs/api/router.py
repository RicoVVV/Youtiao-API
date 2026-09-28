"""接口文档公开 HTTP 接口。

仅暴露文档目录与详情的读取入口；文档内容由应用服务从 Provider 模板与公开协议投影，路由不承载
业务判断。文档页是公开页面，因此两个接口都不要求登录，也不返回密钥、渠道或上游配置。
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.api_docs.api.schemas import ApiDocsDetailQuery, ApiDocsListQuery
from app.modules.api_docs.application.services import ApiDocsApplicationService

router = APIRouter(prefix="/api-docs", tags=["接口文档"])


@router.get("/list", summary="查询接口文档目录")
def list_api_docs(payload: Annotated[ApiDocsListQuery, Depends()]) -> dict[str, object]:
    return ApiDocsApplicationService().list_catalog(**payload.model_dump())


@router.get("/detail", summary="查询接口文档详情")
def get_api_docs_detail(payload: Annotated[ApiDocsDetailQuery, Depends()]) -> dict[str, object]:
    return ApiDocsApplicationService().get_entry(**payload.model_dump())
