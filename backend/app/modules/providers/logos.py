"""供应商公开图标目录与读取。

图标按 ``provider_id`` 只登记一份，同一供应商的多个模板共享同一份资产；新增供应商时在此登记文件名，
并把 SVG 放入 ``assets/logos``。资产保持各家品牌原色且不限定展示尺寸，深浅底适配、着色与容器样式由
前端负责，后端只保证能取到图标内容。
"""

from functools import lru_cache
from pathlib import Path

_LOGO_DIR = Path(__file__).parent / "assets" / "logos"

PROVIDER_LOGO_URL = "/api/providers/logo"
"""图标获取接口路径。

返回相对地址而非绝对地址：浏览器按同源解析，前端无需拼接后端域名，也不依赖请求 Host。
"""

PROVIDER_LOGO_FILES: dict[str, str] = {
    "openai": "openai.svg",
    "google": "google.svg",
    "anthropic": "anthropic.svg",
    "qwen": "qwen.svg",
    "wan": "wan.svg",
    "volcengine": "volcengine.svg",
    "minimax": "minimax.svg",
    "fal": "fal.svg",
}


def provider_logo_url(provider_id: str | None) -> str | None:
    """返回供应商图标的公开地址，未登记图标的供应商返回空值。

    空值表示前端不得为该供应商渲染图标；``provider_id`` 为空表示该模型没有明确供应商。
    """

    if provider_id is None or provider_id not in PROVIDER_LOGO_FILES:
        return None
    return f"{PROVIDER_LOGO_URL}?provider_id={provider_id}"


@lru_cache
def provider_logo_svg(provider_id: str) -> bytes | None:
    """读取供应商图标内容。

    图标随代码发布且不会在运行期变化，因此按供应商缓存读取结果；未登记或资产缺失时返回空值。
    """

    file_name = PROVIDER_LOGO_FILES.get(provider_id)
    if file_name is None:
        return None
    path = _LOGO_DIR / file_name
    if not path.is_file():
        return None
    return path.read_bytes()
