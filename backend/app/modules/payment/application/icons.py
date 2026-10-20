"""支付方式图标的读取用例。"""

from app.core.errors import NotFoundError
from app.modules.payment.icons import payment_icon_svg


class PaymentIconApplicationService:
    """对外提供支付方式图标内容。

    图标是随代码发布的静态资产，用例不读写数据库，只负责把「未登记图标」转换为业务异常，
    由全局异常处理器统一映射为 HTTP 错误。
    """

    def get_icon_svg(self, payment_channel: str, payment_method: str) -> bytes:
        """返回支付方式图标内容，未登记或资产缺失时抛出未找到异常。"""

        svg = payment_icon_svg(payment_channel, payment_method)
        if svg is None:
            raise NotFoundError("支付方式图标不存在")
        return svg
