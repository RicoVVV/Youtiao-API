"""供应商公开 HTTP 接口。

仅暴露供应商图标的获取入口；图标内容由应用服务读取，路由不承载业务判断。
"""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.modules.providers.application.logos import ProviderLogoApplicationService

router = APIRouter(prefix="/providers", tags=["供应商"])


@router.get("/logo", summary="查询供应商图标")
def get_provider_logo(provider_id: Annotated[str, Query(min_length=1, max_length=64)]) -> Response:
    """按供应商标识返回 SVG 图标，未登记图标时返回 404。"""

    svg = ProviderLogoApplicationService().get_logo_svg(provider_id)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )
