"""计费领域数据访问层，集中封装计费记录的查询、行锁、待提交写入与刷新。

本模块不提交或回滚调用方事务，也不处理 HTTP 错误映射；应用服务通过本模块访问计费 ORM，钱包账本访问仍由钱包 CRUD 负责。
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy import select as sqlalchemy_select
from sqlmodel import Session, select

from app.modules.billing.model import BillingAdjustment, Charge, ChargeStatus, PriceQuote, RedemptionCode


class BillingCrud:
    """封装计费领域持久化访问，不管理事务提交或回滚。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方管理的数据库会话。

        参数：session 为当前请求或任务共享的事务会话。
        副作用：不提交、不回滚事务。
        """

        self._session = session

    def add_price_quote(self, quote: PriceQuote) -> PriceQuote:
        """将已构造的报价快照加入当前事务。

        参数：quote 为冻结模型、价格规则与金额后的报价实体。
        返回值：已附加至当前会话的同一实体。
        副作用：仅登记待写入记录，不提交事务。
        """

        self._session.add(quote)
        return quote

    def add_charge(self, charge: Charge) -> Charge:
        """将已构造的扣费单加入当前事务。

        参数：charge 为完成幂等校验后待持久化的扣费单。
        返回值：已附加至当前会话的同一实体。
        副作用：仅登记待写入记录，不提交事务。
        """

        self._session.add(charge)
        return charge

    def add_adjustment(self, adjustment: BillingAdjustment) -> BillingAdjustment:
        """将管理员余额调整记录加入当前事务。

        参数：adjustment 为已关联账本分录的调整记录。
        返回值：已附加至当前会话的同一实体。
        副作用：仅登记待写入记录，不提交事务。
        """

        self._session.add(adjustment)
        return adjustment

    def add_redemption_codes(self, codes: list[RedemptionCode]) -> list[RedemptionCode]:
        """将新生成的兑换码记录加入当前事务，支持一次登记多条。

        参数：codes 为含完整明文兑换码和运营信息的实体列表。
        返回值：已附加至当前会话的同一实体列表。
        副作用：仅登记待写入记录，不提交事务。
        """

        self._session.add_all(codes)
        return codes

    def flush(self) -> None:
        """将当前计费编排已登记的写入刷新至数据库但不提交事务。

        用于在同一事务内取得新账本分录等实体标识后继续组装计费关联记录；数据库约束异常向调用方传播。
        """

        self._session.flush()

    def get_charge_for_video_task(self, task_id: UUID) -> Charge | None:
        """锁定并查询视频任务关联的扣费单，串行化资金状态迁移。"""

        return self._session.scalar(sqlalchemy_select(Charge).where(Charge.video_task_id == task_id).with_for_update())

    def get_redemption_code_for_update(self, code: str) -> RedemptionCode | None:
        """按规范化明文锁定并查询兑换码，避免并发核销重复入账。"""

        return self._session.scalar(
            sqlalchemy_select(RedemptionCode).where(RedemptionCode.code == code).with_for_update()
        )

    def get_redemption_code_by_id(self, code_id: UUID) -> RedemptionCode | None:
        """按主键查询兑换码。

        参数：code_id 为管理端资源标识。
        返回值：匹配的兑换码，不存在时返回空。
        副作用：不修改数据，也不管理事务。
        """

        return self._session.get(RedemptionCode, code_id)

    def list_redemption_codes(
        self, *, page: int, page_size: int, name: str | None, status: str | None, now: datetime
    ) -> tuple[list[RedemptionCode], int]:
        """按管理端筛选条件分页查询兑换码，并返回总数。

        参数：page 和 page_size 控制页码；name 为名称模糊条件；status 为展示状态；now 为统一状态计算时刻。
        返回值：按创建时间和主键倒序排列的记录及筛选后的总数。
        副作用：仅执行读取查询，不提交或回滚事务。
        """

        statement = select(RedemptionCode).where(*_redemption_code_filters(name=name, status=status, now=now))
        total = int(self._session.scalar(sqlalchemy_select(func.count()).select_from(statement.subquery())) or 0)
        items = list(
            self._session.exec(
                statement.order_by(RedemptionCode.created_at.desc(), RedemptionCode.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    def list_redemption_codes_for_export(
        self, *, name: str | None, status: str | None, now: datetime
    ) -> list[RedemptionCode]:
        """按管理端筛选条件查询全部兑换码，供导出使用。

        参数：name 为名称模糊条件；status 为展示状态；now 为统一状态计算时刻。
        返回值：符合筛选条件的全部记录，按创建时间和主键倒序排列。
        副作用：仅执行读取查询，不提交或回滚事务。
        """

        statement = select(RedemptionCode).where(*_redemption_code_filters(name=name, status=status, now=now))
        return list(
            self._session.exec(statement.order_by(RedemptionCode.created_at.desc(), RedemptionCode.id.desc())).all()
        )

    def get_settled_usage_amount(self, user_id: UUID) -> Decimal:
        """汇总用户已结算扣费总额。"""

        amount = self._session.scalar(
            sqlalchemy_select(func.coalesce(func.sum(Charge.settled_amount), 0)).where(
                Charge.user_id == user_id,
                Charge.status == ChargeStatus.settled,
            )
        )
        return Decimal(amount or 0)


def _redemption_code_filters(*, name: str | None, status: str | None, now: datetime) -> list:
    """构造兑换码列表与导出共用的筛选条件。

    参数：name 为名称模糊条件；status 为展示状态；now 为统一状态计算时刻。
    返回值：可直接展开到 where 的筛选表达式列表。
    副作用：不访问数据库，不修改数据。
    """

    filters = []
    if name:
        filters.append(RedemptionCode.name.ilike(f"%{name}%"))
    if status == "redeemed":
        filters.append(RedemptionCode.redeemed_by_user_id.is_not(None))
    elif status == "disabled":
        filters.extend((RedemptionCode.redeemed_by_user_id.is_(None), RedemptionCode.active.is_(False)))
    elif status == "expired":
        filters.extend(
            (
                RedemptionCode.redeemed_by_user_id.is_(None),
                RedemptionCode.active.is_(True),
                RedemptionCode.expires_at.is_not(None),
                RedemptionCode.expires_at <= now,
            )
        )
    elif status == "unused":
        filters.extend(
            (
                RedemptionCode.redeemed_by_user_id.is_(None),
                RedemptionCode.active.is_(True),
                or_(RedemptionCode.expires_at.is_(None), RedemptionCode.expires_at > now),
            )
        )
    return filters
