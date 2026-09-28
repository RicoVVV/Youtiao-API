"""Stripe 美元收款汇率服务，负责自动获取 USD/CNY 汇率并换算 Stripe 美分金额。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from threading import Lock

import httpx
from app.modules.payment.application.errors import PaymentProviderUnavailableError

_USD_CNY_RATE_URL = "https://api.frankfurter.dev/v1/latest"
_USD_CNY_RATE_CACHE_TTL = timedelta(hours=24)
_USD_CURRENCY = "USD"
_CNY_CURRENCY = "CNY"
_CENT_FACTOR = Decimal("100")


@dataclass(frozen=True, slots=True)
class UsdChargeQuote:
    """保存一次人民币支付金额换算出的美元美分和汇率快照。"""

    usd_cents: int
    usd_cny_rate: Decimal


class ExchangeRateService:
    """自动读取 USD/CNY 汇率，并为 Stripe Checkout 生成不可少收的美元美分金额。"""

    def __init__(self) -> None:
        """初始化进程内汇率缓存。

        作用：保存最近一次成功获取的 USD/CNY 汇率，避免每笔 Stripe 报价都访问外部汇率服务。
        使用位置：由 StripePaymentApplicationService 创建，属于 Stripe 报价和下单的汇率准备步骤。
        传入参数：无。
        返回参数：无；创建可复用的汇率服务实例。
        """
        self._cached_rate: Decimal | None = None
        self._cached_at: datetime | None = None
        self._cache_lock = Lock()

    def quote_usd_charge(self, cny_amount: Decimal) -> UsdChargeQuote:
        """将人民币应付金额换算为 Stripe 所需的美元美分金额。

        作用：读取当前有效汇率后，把人民币金额换算成美元美分，并向上取整避免少收款。
        使用位置：StripePaymentApplicationService 的报价和创建 Checkout 流程调用，属于实际收款金额计算步骤。
        传入参数：cny_amount 为按公共定价规则计算出的人民币应付金额。
        返回参数：返回包含美元美分和 USD/CNY 汇率快照的 UsdChargeQuote，供前端展示、Checkout 和回调校验使用。
        """
        usd_cny_rate = self.get_usd_cny_rate()
        usd_cents = (cny_amount / usd_cny_rate * _CENT_FACTOR).to_integral_value(rounding=ROUND_CEILING)
        return UsdChargeQuote(usd_cents=int(usd_cents), usd_cny_rate=usd_cny_rate)

    def get_usd_cny_rate(self) -> Decimal:
        """获取当前有效的 USD/CNY 汇率。

        作用：优先返回 24 小时内的内存缓存；缓存缺失或过期时请求外部汇率服务并更新缓存。
        使用位置：quote_usd_charge 在 Stripe 报价和创建订单时调用，属于动态汇率读取步骤。
        传入参数：无。
        返回参数：返回“1 USD 等于多少 CNY”的正数 Decimal 汇率；外部服务不可用时抛出 PaymentProviderUnavailableError。
        """
        with self._cache_lock:
            now = datetime.now(UTC)
            if (
                self._cached_rate is not None
                and self._cached_at is not None
                and now - self._cached_at < _USD_CNY_RATE_CACHE_TTL
            ):
                return self._cached_rate

            # 只有缓存过期时才请求外部服务，保证同一进程内的订单使用稳定汇率。
            rate = self._fetch_usd_cny_rate()
            self._cached_rate = rate
            self._cached_at = now
            return rate

    @staticmethod
    def _fetch_usd_cny_rate() -> Decimal:
        """从公开汇率服务读取最新 USD/CNY 汇率。

        作用：调用外部汇率接口并校验返回值，确保支付换算不会使用空值、零值或非法数值。
        使用位置：get_usd_cny_rate 在缓存无效时调用，属于汇率缓存刷新步骤。
        传入参数：无。
        返回参数：返回经过校验的正数 Decimal 汇率；请求或响应格式异常时抛出 PaymentProviderUnavailableError。
        """
        try:
            response = httpx.get(
                _USD_CNY_RATE_URL,
                params={"base": _USD_CURRENCY, "symbols": _CNY_CURRENCY},
                timeout=10.0,
            )
            response.raise_for_status()
            rate = Decimal(str(response.json()["rates"][_CNY_CURRENCY]))
        except (httpx.HTTPError, KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise PaymentProviderUnavailableError("USD/CNY 汇率服务暂时不可用") from exc

        if not rate.is_finite() or rate <= 0:
            raise PaymentProviderUnavailableError("USD/CNY 汇率服务返回无效汇率")
        return rate

    @staticmethod
    def format_usd_cents(usd_cents: int) -> str:
        """将 Stripe 美分金额格式化为前端可展示的美元字符串。

        作用：把 Stripe 使用的整数美分转换为两位小数美元文本，避免前端自行处理最小货币单位。
        使用位置：StripePaymentApplicationService 组织报价和下单响应时调用，属于接口响应格式化步骤。
        传入参数：usd_cents 为 Stripe Checkout 使用的整数美元美分。
        返回参数：返回固定两位小数的美元金额字符串，例如 1370 返回 "13.70"。
        """
        return f"{Decimal(usd_cents) / _CENT_FACTOR:.2f}"
