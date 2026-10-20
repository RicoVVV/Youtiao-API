"""支付方式内置图标目录与读取。

图标按支付方式登记文件名，同一支付方式在多个渠道复用同一份资产；新增支付方式时在此登记，
并把 SVG 放入 ``assets/icons``。资产保持各渠道品牌原色且不限定展示尺寸，深浅底适配、着色与
容器样式由前端负责，后端只保证能取到图标内容。
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

_ICON_DIR = Path(__file__).parent / "assets" / "icons"

PAYMENT_ICON_URL = "/api/payments/icon"
"""图标获取接口路径。

返回相对地址而非绝对地址：浏览器按同源解析，前端无需拼接后端域名，也不依赖请求 Host。
"""

PAYMENT_METHOD_ICON_FILES: dict[str, str] = {
    "page_pay": "alipay.svg",
    "alipay": "alipay.svg",
    "wxpay": "wxpay.svg",
    "unionpay": "unionpay.svg",
    "card": "card.svg",
    "crypto": "crypto.svg",
    "usdt-tron": "usdt.svg",
}
"""支付方式到图标文件的精确匹配表。"""

CHANNEL_DEFAULT_ICON_FILES: dict[str, str] = {
    "alipay_official": "alipay.svg",
    "allinpay": "unionpay.svg",
    "stripe": "card.svg",
    "shieldz": "crypto.svg",
    "dspay": "crypto.svg",
    "gmpay": "usdt.svg",
}
"""支付渠道的兜底图标，用于未在精确匹配表中登记的支付方式。"""

_STABLECOIN_PREFIXES = ("usdt", "usdc")
"""稳定币支付方式前缀，形如 ``usdt-tron``、``usdc-ethereum`` 时复用 USDT 图标。"""


def payment_icon_file(payment_channel: str, payment_method: str) -> str | None:
    """按支付渠道和支付方式解析内置图标文件名，未登记时返回空值。

    解析优先级：精确匹配支付方式 -> 稳定币前缀（usdt/usdc）-> 渠道默认图标。
    空值表示没有可用的内置图标，调用方应回退到管理员配置值。
    """

    if payment_method in PAYMENT_METHOD_ICON_FILES:
        return PAYMENT_METHOD_ICON_FILES[payment_method]
    if payment_method.lower().startswith(_STABLECOIN_PREFIXES):
        return "usdt.svg"
    return CHANNEL_DEFAULT_ICON_FILES.get(payment_channel)


def payment_icon_url(payment_channel: str, payment_method: str) -> str | None:
    """返回支付方式内置图标的公开地址，未登记图标时返回空值。

    空值表示前端不得为该支付方式渲染内置图标；调用方应继续使用管理员配置值。
    """

    if payment_icon_file(payment_channel, payment_method) is None:
        return None
    query = urlencode({"payment_channel": payment_channel, "payment_method": payment_method})
    return f"{PAYMENT_ICON_URL}?{query}"


@lru_cache
def payment_icon_svg(payment_channel: str, payment_method: str) -> bytes | None:
    """读取支付方式图标内容。

    图标随代码发布且不会在运行期变化，因此按渠道和支付方式缓存读取结果；未登记或资产缺失时返回空值。
    """

    file_name = payment_icon_file(payment_channel, payment_method)
    if file_name is None:
        return None
    path = _ICON_DIR / file_name
    if not path.is_file():
        return None
    return path.read_bytes()
