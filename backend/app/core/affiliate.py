"""邀请返利领域常量与纯函数，供模型默认值、系统设置和返利计算共用。

本模块不依赖数据库、HTTP 或具体业务服务，只承载可独立测试的规则。
"""

import secrets
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

AFFILIATE_CODE_LENGTH = 12
AFFILIATE_CODE_MIN_LENGTH = 4
AFFILIATE_CODE_MAX_LENGTH = 32
AFFILIATE_CODE_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
AFFILIATE_CODE_ALLOWED_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

DEFAULT_AFFILIATE_ENABLED = False
DEFAULT_REBATE_RATE_PERCENT = Decimal("5.00")
MIN_REBATE_RATE_PERCENT = Decimal("0.00")
MAX_REBATE_RATE_PERCENT = Decimal("100.00")
DEFAULT_REBATE_FREEZE_HOURS = 5
MAX_REBATE_FREEZE_HOURS = 720
DEFAULT_REBATE_DURATION_DAYS = 0
MAX_REBATE_DURATION_DAYS = 3650
DEFAULT_REBATE_PER_INVITEE_CAP = Decimal("0.000000")
DEFAULT_SIGNUP_BONUS = Decimal("0.000000")
MAX_SIGNUP_BONUS = Decimal("1000000.000000")

MONEY_QUANT = Decimal("0.000001")
RATE_QUANT = Decimal("0.01")


def normalize_affiliate_code(raw: str | None) -> str:
    """统一去除首尾空白并转为大写，空值返回空字符串。"""

    return (raw or "").strip().upper()


def is_valid_affiliate_code(code: str | None) -> bool:
    """校验邀请码长度与字符集；调用方需先完成大小写归一化。"""

    normalized = normalize_affiliate_code(code)
    if not AFFILIATE_CODE_MIN_LENGTH <= len(normalized) <= AFFILIATE_CODE_MAX_LENGTH:
        return False
    return all(char in AFFILIATE_CODE_ALLOWED_CHARS for char in normalized)


def generate_affiliate_code() -> str:
    """生成系统随机邀请码，排除易混淆字符。"""

    return "".join(secrets.choice(AFFILIATE_CODE_CHARSET) for _ in range(AFFILIATE_CODE_LENGTH))


def clamp_rebate_rate(value: Decimal | float | int | str | None) -> Decimal:
    """把返利比例限制在 0–100；无法解析时回退默认比例。"""

    if value is None:
        return DEFAULT_REBATE_RATE_PERCENT
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return DEFAULT_REBATE_RATE_PERCENT
    if not rate.is_finite():
        return DEFAULT_REBATE_RATE_PERCENT
    return min(max(rate, MIN_REBATE_RATE_PERCENT), MAX_REBATE_RATE_PERCENT).quantize(RATE_QUANT)


def calculate_rebate(
    base_amount: Decimal | float | int | str | None, rate_percent: Decimal | float | int | str | None
) -> Decimal:
    """按 USD 金额与百分比计算返利，结果固定保留 6 位小数。"""

    if base_amount is None:
        return Decimal("0.000000")
    try:
        base = Decimal(str(base_amount))
    except (InvalidOperation, ValueError):
        return Decimal("0.000000")
    if not base.is_finite() or base <= 0:
        return Decimal("0.000000")
    rate = clamp_rebate_rate(rate_percent)
    if rate <= 0:
        return Decimal("0.000000")
    return (base * rate / Decimal("100")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def mask_identity(value: str | None) -> str:
    """对用户名或邮箱做最小化脱敏，避免邀请人列表泄露被邀请人身份。"""

    text = (value or "").strip()
    if not text:
        return "***"
    if "@" not in text:
        return f"{text[0]}***"
    local, domain = text.split("@", 1)
    masked_local = f"{local[0]}***" if local else "***"
    if "." not in domain:
        return f"{masked_local}@***"
    domain_name, suffix = domain.rsplit(".", 1)
    masked_domain = f"{domain_name[0]}***" if domain_name else "***"
    return f"{masked_local}@{masked_domain}.{suffix}"
