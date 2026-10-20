"""管理员维护会员等级、套餐、专享分组，以及授予与撤销用户会员的事务用例。"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from app.core.errors import NotFoundError, ValidationError
from app.modules.membership.application.services import (
    MembershipApplicationService,
    MembershipQueryService,
    MembershipViews,
)
from app.modules.membership.crud import MembershipCrud
from app.modules.membership.model import (
    MembershipLevel,
    MembershipPeriod,
    MembershipPlan,
    MembershipRecord,
    MembershipRecordSource,
    UserMembership,
)
from app.modules.wallet.application.services import WalletApplicationService
from app.modules.wallet.model import BalanceRecordType


class AdminMembershipApplicationService:
    """提供管理员会员配置与用户会员变更用例，写操作自行管理事务。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话并初始化会员仓储。"""

        self._session = session
        self._crud = MembershipCrud(session)

    # 等级

    def list_levels(
        self, is_public: bool | None, is_active: bool | None, page: int, page_size: int
    ) -> tuple[int, list[dict]]:
        """分页查询等级，包含隐藏等级、套餐与专享分组。"""

        total, levels = self._crud.list_levels_page(
            is_public=is_public, is_active=is_active, page=page, page_size=page_size
        )
        return total, self._to_level_views(levels)

    def get_level_detail(self, level_id: UUID) -> dict:
        """返回等级详情，含套餐与专享分组。"""

        return self._to_level_views([self._require_level(level_id)])[0]

    def create_level(
        self,
        *,
        code: str,
        name: str,
        description: str,
        rank: int,
        is_public: bool,
        is_active: bool,
        plans: list[dict] | None,
        group_ids: list[int] | None,
    ) -> dict:
        """创建等级，可在同一事务中创建套餐与关联专享分组。"""

        try:
            if self._crud.get_level_by_code(code) is not None:
                raise ValidationError("会员等级编码已存在")
            plans = plans or []
            periods = [MembershipPeriod(item["period"]) for item in plans]
            if len(set(periods)) != len(periods):
                raise ValidationError("同一等级每种时长只能配置一个套餐")
            for item in plans:
                self._validate_plan_price(is_public, item["price"])
            if group_ids:
                self._validate_group_ids(group_ids)
            level = self._crud.add_level(
                MembershipLevel(
                    code=code,
                    name=name,
                    description=description,
                    rank=rank,
                    is_public=is_public,
                    is_active=is_active,
                )
            )
            for item in plans:
                self._crud.add_plan(
                    MembershipPlan(
                        level_id=level.id,
                        period=MembershipPeriod(item["period"]),
                        price=item["price"],
                        bonus_amount=item["bonus_amount"],
                        is_active=item["is_active"],
                    )
                )
            if group_ids:
                self._crud.replace_level_groups(level.id, group_ids)
            result = self._to_level_views([level])[0]
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def update_level(
        self,
        *,
        level_id: UUID,
        name: str | None,
        description: str | None,
        rank: int | None,
        is_public: bool | None,
        group_ids: list[int] | None,
    ) -> dict:
        """按字段更新等级；group_ids 提供时整体替换专享分组。"""

        try:
            level = self._require_level(level_id)
            if is_public is True and not level.is_public:
                for plan in self._crud.list_plans_by_level_ids({level.id}):
                    self._validate_plan_price(True, plan.price)
            if group_ids is not None:
                self._validate_group_ids(group_ids)
            if name is not None:
                level.name = name
            if description is not None:
                level.description = description
            if rank is not None:
                level.rank = rank
            if is_public is not None:
                level.is_public = is_public
            if group_ids is not None:
                self._crud.replace_level_groups(level.id, group_ids)
            self._crud.flush()
            result = self._to_level_views([level])[0]
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def update_level_status(self, *, level_id: UUID, is_active: bool) -> dict:
        """启用或停用等级；停用不影响已开通会员。"""

        try:
            level = self._require_level(level_id)
            level.is_active = is_active
            self._crud.flush()
            result = self._to_level_views([level])[0]
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def delete_level(self, *, level_id: UUID) -> None:
        """逻辑删除等级及其套餐；仍有有效会员时拒绝。"""

        try:
            level = self._require_level(level_id)
            if self._crud.count_active_members_by_level(level.id, datetime.now(UTC)) > 0:
                raise ValidationError("该等级仍有有效会员，不能删除")
            self._crud.delete_plans_by_level(level.id)
            level.is_del = True
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    # 套餐

    def create_plan(
        self, *, level_id: UUID, period: str, price: Decimal, bonus_amount: Decimal, is_active: bool
    ) -> dict:
        """为等级新增套餐，同等级同时长不可重复。"""

        try:
            level = self._require_level(level_id)
            self._validate_plan_price(level.is_public, price)
            if self._crud.get_plan_by_level_period(level.id, MembershipPeriod(period)) is not None:
                raise ValidationError("同一等级每种时长只能配置一个套餐")
            plan = self._crud.add_plan(
                MembershipPlan(
                    level_id=level.id,
                    period=MembershipPeriod(period),
                    price=price,
                    bonus_amount=bonus_amount,
                    is_active=is_active,
                )
            )
            result = self._to_plan_view(plan)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def update_plan(self, *, plan_id: UUID, price: Decimal | None, bonus_amount: Decimal | None) -> dict:
        """更新套餐价格与赠送额。"""

        try:
            plan = self._require_plan(plan_id)
            if price is not None:
                self._validate_plan_price(self._require_level(plan.level_id).is_public, price)
                plan.price = price
            if bonus_amount is not None:
                plan.bonus_amount = bonus_amount
            self._crud.flush()
            result = self._to_plan_view(plan)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def update_plan_status(self, *, plan_id: UUID, is_active: bool) -> dict:
        """启用或停用套餐。"""

        try:
            plan = self._require_plan(plan_id)
            plan.is_active = is_active
            self._crud.flush()
            result = self._to_plan_view(plan)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def delete_plan(self, *, plan_id: UUID) -> None:
        """逻辑删除套餐；待支付订单结算时按下单冻结金额执行。"""

        try:
            plan = self._require_plan(plan_id)
            plan.is_del = True
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    # 用户会员

    def list_user_memberships(
        self, user_id: UUID | None, level_id: UUID | None, is_active: bool | None, page: int, page_size: int
    ) -> tuple[int, list[dict]]:
        """分页查询用户会员状态。"""

        now = datetime.now(UTC)
        total, items = self._crud.list_user_memberships_page(
            user_id=user_id, level_id=level_id, is_active=is_active, now=now, page=page, page_size=page_size
        )
        levels = {level.id: level for level in self._crud.list_levels_by_ids({item.level_id for item in items})}
        return total, [self._to_user_membership_view(item, levels.get(item.level_id), now) for item in items]

    def list_records(self, user_id: UUID | None, page: int, page_size: int) -> tuple[int, list[dict]]:
        """分页查询会员流水。"""

        return MembershipQueryService(self._session).list_records_page(user_id, page, page_size)

    def grant(
        self, *, user_id: UUID, plan_id: UUID, quantity: int, grant_bonus: bool, reason: str, operator_id: UUID
    ) -> dict:
        """授予会员：同级顺延，不同等级从当前时间替换，可选赠送余额。"""

        try:
            if self._crud.get_user(user_id) is None:
                raise NotFoundError("用户不存在")
            plan = self._require_plan(plan_id)
            level = self._require_level(plan.level_id)
            if not plan.is_active or not level.is_active:
                raise ValidationError("会员套餐已停用")
            now = datetime.now(UTC)
            membership = self._crud.get_user_membership_for_update(user_id)
            expires_before = None if membership is None else membership.expires_at
            delta = MembershipApplicationService.period_delta(plan.period, quantity)
            if membership is not None and membership.expires_at > now and membership.level_id == level.id:
                started_at, expires_at = membership.started_at, membership.expires_at + delta
            else:
                started_at, expires_at = now, now + delta
            if membership is None:
                membership = self._crud.add_user_membership(
                    UserMembership(user_id=user_id, level_id=level.id, started_at=started_at, expires_at=expires_at)
                )
            else:
                membership.level_id = level.id
                membership.started_at = started_at
                membership.expires_at = expires_at
            bonus = plan.bonus_amount * quantity if grant_bonus else Decimal("0")
            record = self._crud.add_record(
                MembershipRecord(
                    user_id=user_id,
                    source=MembershipRecordSource.admin_grant,
                    level_id=level.id,
                    plan_id=plan.id,
                    quantity=quantity,
                    expires_before=expires_before,
                    expires_after=expires_at,
                    bonus_amount=bonus,
                    operator_id=operator_id,
                    reason=reason,
                )
            )
            if bonus > 0:
                WalletApplicationService(self._session).grant(
                    user_id=user_id,
                    amount=bonus,
                    record_type=BalanceRecordType.membership_bonus,
                    reason=f"管理员授予会员 {level.name} 赠送余额",
                    operator_id=operator_id,
                    membership_record_id=record.id,
                )
            self._crud.flush()
            result = self._to_user_membership_view(membership, level, now)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    def revoke(self, *, user_id: UUID, reason: str, operator_id: UUID) -> dict:
        """撤销有效会员：到期时间置为当前时间，已赠送余额不回收。"""

        try:
            now = datetime.now(UTC)
            membership = self._crud.get_user_membership_for_update(user_id)
            if membership is None or membership.expires_at <= now:
                raise ValidationError("用户当前没有有效会员")
            expires_before = membership.expires_at
            membership.expires_at = now
            self._crud.add_record(
                MembershipRecord(
                    user_id=user_id,
                    source=MembershipRecordSource.admin_revoke,
                    level_id=membership.level_id,
                    expires_before=expires_before,
                    expires_after=now,
                    operator_id=operator_id,
                    reason=reason,
                )
            )
            level = self._crud.get_level(membership.level_id, include_deleted=True)
            result = self._to_user_membership_view(membership, level, now)
            self._session.commit()
            return result
        except Exception:
            self._session.rollback()
            raise

    # 内部

    def _require_level(self, level_id: UUID) -> MembershipLevel:
        """读取未删除等级，不存在时抛出 404。"""

        level = self._crud.get_level(level_id)
        if level is None:
            raise NotFoundError("会员等级不存在")
        return level

    def _require_plan(self, plan_id: UUID) -> MembershipPlan:
        """读取未删除套餐，不存在时抛出 404。"""

        plan = self._crud.get_plan(plan_id)
        if plan is None:
            raise NotFoundError("会员套餐不存在")
        return plan

    def _validate_group_ids(self, group_ids: list[int]) -> None:
        """校验专享分组无重复、均存在且为 restricted。"""

        if len(set(group_ids)) != len(group_ids):
            raise ValidationError("专享分组不可重复")
        groups = self._crud.list_token_groups(set(group_ids))
        if len(groups) != len(group_ids):
            raise ValidationError("专享分组不存在")
        if any(group.visibility != "restricted" for group in groups):
            raise ValidationError("专享分组必须为受限分组")

    @staticmethod
    def _validate_plan_price(is_public: bool, price: Decimal) -> None:
        """公开等级的套餐售价必须大于 0。"""

        if is_public and price <= 0:
            raise ValidationError("公开等级的套餐售价必须大于 0")

    def _to_level_views(self, levels: list[MembershipLevel]) -> list[dict]:
        """批量组装等级管理投影，含套餐与专享分组。"""

        level_ids = {level.id for level in levels}
        plans: dict[UUID, list[dict]] = {level_id: [] for level_id in level_ids}
        for plan in self._crud.list_plans_by_level_ids(level_ids):
            plans[plan.level_id].append(self._to_plan_view(plan))
        groups: dict[UUID, list[dict]] = {level_id: [] for level_id in level_ids}
        for level_id, group in self._crud.list_groups_by_level_ids(level_ids):
            groups[level_id].append(MembershipViews.group(group))
        return [
            {
                **MembershipViews.level(level),
                "is_public": level.is_public,
                "is_active": level.is_active,
                "created_at": level.created_at,
                "updated_at": level.updated_at,
                "plans": plans[level.id],
                "groups": groups[level.id],
            }
            for level in levels
        ]

    @staticmethod
    def _to_plan_view(plan: MembershipPlan) -> dict:
        """组装套餐管理投影。"""

        return {
            **MembershipViews.plan(plan),
            "level_id": plan.level_id,
            "is_active": plan.is_active,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

    @staticmethod
    def _to_user_membership_view(membership: UserMembership, level: MembershipLevel | None, now: datetime) -> dict:
        """组装用户会员管理投影。"""

        return {
            "id": membership.id,
            "user_id": membership.user_id,
            "level_id": membership.level_id,
            "level_code": None if level is None else level.code,
            "level_name": None if level is None else level.name,
            "started_at": membership.started_at,
            "expires_at": membership.expires_at,
            "is_active": membership.expires_at > now,
        }
