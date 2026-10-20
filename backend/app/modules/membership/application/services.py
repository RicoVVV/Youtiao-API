"""会员查询、购买校验与支付结算用例。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.membership.crud import MembershipCrud
from app.modules.membership.model import (
    PERIOD_DAYS,
    MembershipLevel,
    MembershipPeriod,
    MembershipPlan,
    MembershipRecord,
    MembershipRecordSource,
    UserMembership,
)
from app.modules.user.model.token_group import TokenGroup
from app.modules.wallet.application.services import WalletApplicationService
from app.modules.wallet.model import BalanceRecordType, RechargeOrder

CHANGE_OPEN = "open"
CHANGE_RENEW = "renew"
CHANGE_UPGRADE = "upgrade"
CHANGE_DOWNGRADE = "downgrade"


class MembershipQueryService:
    """提供用户会员状态、套餐列表与流水的只读查询。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话并初始化会员仓储。"""

        self._crud = MembershipCrud(session)

    def get_active_membership(self, user_id: UUID) -> dict:
        """返回用户会员状态、等级、有效期与专享分组。"""

        membership = self._crud.get_user_membership(user_id)
        level = None if membership is None else self._crud.get_level(membership.level_id)
        if membership is None or level is None:
            return {
                "is_active": False,
                "level": None,
                "started_at": None,
                "expires_at": None,
                "groups": [],
            }
        is_active = membership.expires_at > datetime.now(UTC)
        groups = self._crud.list_groups_by_level_ids({level.id}) if is_active else []
        return {
            "is_active": is_active,
            "level": MembershipViews.level(level),
            "started_at": membership.started_at,
            "expires_at": membership.expires_at,
            "groups": [MembershipViews.group(group) for _, group in groups],
        }

    def list_public_plans(self) -> list[dict]:
        """按等级聚合返回可购买套餐与专享分组。"""

        levels: dict[UUID, dict] = {}
        for plan, level in self._crud.list_public_active_plans():
            item = levels.setdefault(level.id, {**MembershipViews.level(level), "groups": [], "plans": []})
            item["plans"].append(MembershipViews.plan(plan))
        for level_id, group in self._crud.list_groups_by_level_ids(set(levels)):
            levels[level_id]["groups"].append(MembershipViews.group(group))
        return list(levels.values())

    def list_records_page(self, user_id: UUID | None, page: int, page_size: int) -> tuple[int, list[dict]]:
        """分页返回会员流水投影，user_id 为空时查询全部。"""

        total, records = self._crud.list_records_page(user_id=user_id, page=page, page_size=page_size)
        levels = {level.id: level for level in self._crud.list_levels_by_ids({item.level_id for item in records})}
        return total, [MembershipViews.record(item, levels.get(item.level_id)) for item in records]

    def get_order_results(self, order_ids: set[UUID]) -> dict[UUID, dict]:
        """按支付订单批量返回会员购买结果，供支付流水展示；无结果的订单不在返回中。"""

        records = self._crud.list_records_by_order_ids(order_ids)
        levels = {level.id: level for level in self._crud.list_levels_by_ids({item.level_id for item in records})}
        return {
            item.recharge_order_id: MembershipViews.order_result(item, levels.get(item.level_id)) for item in records
        }


class MembershipApplicationService:
    """提供会员下单校验与支付结算用例，不自行提交事务。"""

    def __init__(self, session: Session) -> None:
        """接收调用方管理的会话。"""

        self._session = session
        self._crud = MembershipCrud(session)

    @staticmethod
    def period_delta(period: MembershipPeriod, quantity: int) -> timedelta:
        """按固定天数换算时长份数。"""

        return timedelta(days=PERIOD_DAYS[MembershipPeriod(period)] * quantity)

    @staticmethod
    def compute_change(
        current_rank: int | None,
        current_expires_at: datetime | None,
        target_rank: int,
        same_level: bool,
        delta: timedelta,
        now: datetime,
    ) -> tuple[str, datetime | None, datetime | None]:
        """计算会员变更类型与新的起止时间；续费时起始时间为 None 表示保持不变，降级时均为 None。"""

        if current_rank is None or current_expires_at is None or current_expires_at <= now:
            return CHANGE_OPEN, now, now + delta
        if same_level:
            return CHANGE_RENEW, None, current_expires_at + delta
        if target_rank > current_rank:
            return CHANGE_UPGRADE, now, now + delta
        return CHANGE_DOWNGRADE, None, None

    def ensure_purchasable(self, user_id: UUID, plan_id: UUID) -> tuple[MembershipPlan, MembershipLevel]:
        """校验套餐可对外售卖且购买不构成降级。"""

        plan = self._crud.get_plan(plan_id)
        level = None if plan is None else self._crud.get_level(plan.level_id)
        if plan is None or level is None or not level.is_public:
            raise NotFoundError("会员套餐不存在")
        if not plan.is_active or not level.is_active:
            raise ValidationError("会员套餐已停用")
        if plan.price <= 0:
            raise ValidationError("会员套餐价格未配置")
        now = datetime.now(UTC)
        membership = self._crud.get_user_membership(user_id)
        current_level = None if membership is None else self._crud.get_level(membership.level_id, include_deleted=True)
        kind, _, _ = self.compute_change(
            None if current_level is None else current_level.rank,
            None if membership is None else membership.expires_at,
            level.rank,
            membership is not None and membership.level_id == level.id,
            self.period_delta(plan.period, 1),
            now,
        )
        if kind == CHANGE_DOWNGRADE:
            raise ValidationError("当前会员等级更高，不支持购买低等级会员")
        return plan, level

    def apply_purchase(self, order: RechargeOrder) -> MembershipRecord:
        """在支付结算事务内开通、续费或升级会员；结算时构成降级则将订单金额转入余额。"""

        existing = self._crud.get_record_by_order_id(order.id)
        if existing is not None:
            return existing
        plan = self._crud.get_plan(order.membership_plan_id, include_deleted=True)
        if plan is None:
            raise NotFoundError("会员套餐不存在")
        level = self._crud.get_level(plan.level_id, include_deleted=True)
        if level is None:
            raise NotFoundError("会员等级不存在")
        now = datetime.now(UTC)
        membership = self._crud.get_user_membership_for_update(order.user_id)
        current_level = None if membership is None else self._crud.get_level(membership.level_id, include_deleted=True)
        expires_before = None if membership is None else membership.expires_at
        kind, started_at, expires_at = self.compute_change(
            None if current_level is None else current_level.rank,
            expires_before,
            level.rank,
            membership is not None and membership.level_id == level.id,
            self.period_delta(plan.period, 1),
            now,
        )
        wallet = WalletApplicationService(self._session)
        if kind == CHANGE_DOWNGRADE:
            record = self._crud.add_record(
                MembershipRecord(
                    user_id=order.user_id,
                    source=MembershipRecordSource.purchase_converted,
                    level_id=level.id,
                    plan_id=plan.id,
                    expires_before=expires_before,
                    expires_after=expires_before,
                    recharge_order_id=order.id,
                    reason="结算时构成降级，订单金额转入余额",
                )
            )
            wallet.grant(
                user_id=order.user_id,
                amount=order.amount,
                record_type=BalanceRecordType.recharge,
                reason="会员订单结算时构成降级，订单金额转入余额",
                recharge_order_id=order.id,
            )
            return record
        self._apply_membership(membership, order.user_id, level.id, started_at, expires_at)
        record = self._crud.add_record(
            MembershipRecord(
                user_id=order.user_id,
                source=MembershipRecordSource.purchase,
                level_id=level.id,
                plan_id=plan.id,
                expires_before=expires_before,
                expires_after=expires_at,
                bonus_amount=plan.bonus_amount,
                recharge_order_id=order.id,
                reason=f"购买会员 {level.name}",
            )
        )
        if plan.bonus_amount > 0:
            wallet.grant(
                user_id=order.user_id,
                amount=plan.bonus_amount,
                record_type=BalanceRecordType.membership_bonus,
                reason=f"开通会员 {level.name} 赠送余额",
                membership_record_id=record.id,
            )
        return record

    def _apply_membership(
        self,
        membership: UserMembership | None,
        user_id: UUID,
        level_id: UUID,
        started_at: datetime | None,
        expires_at: datetime,
    ) -> None:
        """写入用户会员行；started_at 为 None 时保持原起始时间。"""

        if membership is None:
            self._crud.add_user_membership(
                UserMembership(user_id=user_id, level_id=level_id, started_at=started_at, expires_at=expires_at)
            )
            return
        membership.level_id = level_id
        if started_at is not None:
            membership.started_at = started_at
        membership.expires_at = expires_at
        self._crud.flush()


class MembershipViews:
    """会员领域对象到接口投影的组装，不返回敏感字段。"""

    @staticmethod
    def level(level: MembershipLevel) -> dict:
        """构建等级展示投影。"""

        return {
            "id": level.id,
            "code": level.code,
            "name": level.name,
            "description": level.description,
            "rank": level.rank,
        }

    @staticmethod
    def plan(plan: MembershipPlan) -> dict:
        """构建套餐展示投影，金额以字符串返回。"""

        return {
            "id": plan.id,
            "period": MembershipPeriod(plan.period).value,
            "price": MembershipViews.amount(plan.price),
            "bonus_amount": MembershipViews.amount(plan.bonus_amount),
        }

    @staticmethod
    def group(group: TokenGroup) -> dict:
        """构建专享分组展示投影。"""

        return {"id": group.id, "name": group.name}

    @staticmethod
    def record(record: MembershipRecord, level: MembershipLevel | None) -> dict:
        """构建会员流水展示投影。"""

        return {
            "id": record.id,
            "user_id": record.user_id,
            "source": MembershipRecordSource(record.source).value,
            "level_id": record.level_id,
            "level_name": None if level is None else level.name,
            "plan_id": record.plan_id,
            "quantity": record.quantity,
            "expires_before": record.expires_before,
            "expires_after": record.expires_after,
            "bonus_amount": MembershipViews.amount(record.bonus_amount),
            "recharge_order_id": record.recharge_order_id,
            "operator_id": record.operator_id,
            "reason": record.reason,
            "created_at": record.created_at,
        }

    @staticmethod
    def order_result(record: MembershipRecord, level: MembershipLevel | None) -> dict:
        """构建支付流水中会员订单的购买结果投影。"""

        return {
            "source": MembershipRecordSource(record.source).value,
            "level_id": record.level_id,
            "level_name": None if level is None else level.name,
            "expires_before": record.expires_before,
            "expires_after": record.expires_after,
            "bonus_amount": MembershipViews.amount(record.bonus_amount),
        }

    @staticmethod
    def amount(amount: Decimal) -> str:
        """将金额格式化为两位小数字符串。"""

        return f"{amount:.2f}"
