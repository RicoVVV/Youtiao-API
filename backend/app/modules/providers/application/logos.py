"""供应商图标的读取用例。"""

from app.core.errors import NotFoundError
from app.modules.providers.logos import provider_logo_svg


class ProviderLogoApplicationService:
    """对外提供供应商图标内容。

    图标是随代码发布的静态资产，用例不读写数据库，只负责把「未登记图标」转换为业务异常，
    由全局异常处理器统一映射为 HTTP 错误。
    """

    def get_logo_svg(self, provider_id: str) -> bytes:
        """返回供应商图标内容，未登记或资产缺失时抛出未找到异常。"""

        svg = provider_logo_svg(provider_id)
        if svg is None:
            raise NotFoundError("供应商图标不存在")
        return svg
