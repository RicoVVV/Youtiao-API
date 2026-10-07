"""支付完成跳转地址处理，负责为前端地址追加本地订单号。"""

from urllib.parse import quote, urlsplit, urlunsplit


def append_order_no(return_url: str, order_no: str) -> str:
    """在支付完成跳转地址中追加订单号查询参数。

    作用：保留前端传入地址的原有路径和查询参数，并追加本地订单号。
    使用位置：三种支付应用服务生成订单号后调用，再把最终地址交给支付网关和响应组装逻辑。
    传入参数：return_url 为前端传入的基础跳转地址；order_no 为服务端生成的本地订单号。
    返回参数：返回包含 `order_no` 查询参数的最终跳转地址。
    """
    parts = urlsplit(return_url)
    separator = "&" if parts.query else ""
    query = f"{parts.query}{separator}order_no={quote(order_no, safe='')}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
