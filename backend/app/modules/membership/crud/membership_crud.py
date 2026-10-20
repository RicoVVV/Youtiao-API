"""会员等级、套餐、专享分组、用户会员与会员流水的数据库访问。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlmodel import Session

from app.modules.membership.model import (
    MembershipLevel,
    MembershipLevelGroup,
    MembershipPlan,
    MembershipRecord,
    UserMembership,
)
from app.modules.user.model.token_group import TokenGroup
from app.modules.user.model.user import User


class MembershipCrud:
    """封装会员相关表的查询、锁定与持久化。"""

    def __init__(self, session: Session) -> None:
        """绑定调用方提供的事务会话。"""

        self._session = session

    def flush(self) -> None:
        """刷新待写入对象，获取主键并触发约束校验。"""

        self._session.flush()

    # 等级

    def get_level(self, level_id: UUID, *, include_deleted: bool = False) -> MembershipLevel | None:
        """读取指定等级，可选包含已逻辑删除记录。"""

        return self._session.scalar(
            select(MembershipLevel)
            .where(MembershipLevel.id == level_id)
            .execution_options(include_deleted=include_deleted)
        )

    def get_level_by_code(self, code: str) -> MembershipLevel | None:
        """按编码读取未删除等级。"""

        return self._session.scalar(select(MembershipLevel).where(MembershipLevel.code == code))

    def list_levels_by_ids(self, level_ids: set[UUID]) -> list[MembershipLevel]:
        """批量读取等级，包含已逻辑删除记录以便展示历史。"""

        if not level_ids:
            return []
        return list(
            self._session.scalars(
                select(MembershipLevel).where(MembershipLevel.id.in_(level_ids)).execution_options(include_deleted=True)
            )
        )

    def list_levels_page(
        self, *, is_public: bool | None, is_active: bool | None, page: int, page_size: int
    ) -> tuple[int, list[MembershipLevel]]:
        """按 rank 分页读取未删除等级及总数。"""

        conditions = []
        if is_public is not None:
            conditions.append(MembershipLevel.is_public.is_(is_public))
        if is_active is not None:
            conditions.append(MembershipLevel.is_active.is_(is_active))
        total = self._session.scalar(select(func.count()).select_from(MembershipLevel).where(*conditions)) or 0
        items = list(
            self._session.scalars(
                select(MembershipLevel)
                .where(*conditions)
                .order_by(MembershipLevel.rank, MembershipLevel.code)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    def add_level(self, level: MembershipLevel) -> MembershipLevel:
        """新增等级并刷新主键。"""

        self._session.add(level)
        self._session.flush()
        return level

    # 套餐

    def get_plan(self, plan_id: UUID, *, include_deleted: bool = False) -> MembershipPlan | None:
        """读取指定套餐，可选包含已逻辑删除记录。"""

        return self._session.scalar(
            select(MembershipPlan)
            .where(MembershipPlan.id == plan_id)
            .execution_options(include_deleted=include_deleted)
        )

    def get_plan_by_level_period(self, level_id: UUID, period) -> MembershipPlan | None:
        """读取等级在指定时长下的未删除套餐。"""

        return self._session.scalar(
            select(MembershipPlan).where(MembershipPlan.level_id == level_id, MembershipPlan.period == period)
        )

    def list_plans_by_level_ids(self, level_ids: set[UUID]) -> list[MembershipPlan]:
        """批量读取等级下的未删除套餐。"""

        if not level_ids:
            return []
        return list(
            self._session.scalars(
                select(MembershipPlan)
                .where(MembershipPlan.level_id.in_(level_ids))
                .order_by(MembershipPlan.level_id, MembershipPlan.period)
            )
        )

    def list_public_active_plans(self) -> list[tuple[MembershipPlan, MembershipLevel]]:
        """读取公开且启用等级下的启用套餐，按等级 rank 与时长排序。"""

        return list(
            self._session.execute(
                select(MembershipPlan, MembershipLevel)
                .join(MembershipLevel, MembershipLevel.id == MembershipPlan.level_id)
                .where(
                    MembershipPlan.is_active.is_(True),
                    MembershipLevel.is_active.is_(True),
                    MembershipLevel.is_public.is_(True),
                    MembershipLevel.is_del.is_(False),
                )
                .order_by(MembershipLevel.rank, MembershipPlan.period)
            ).all()
        )

    def add_plan(self, plan: MembershipPlan) -> MembershipPlan:
        """新增套餐并刷新主键。"""

        self._session.add(plan)
        self._session.flush()
        return plan

    def delete_plans_by_level(self, level_id: UUID) -> None:
        """逻辑删除等级下的全部套餐。"""

        self._session.execute(
            update(MembershipPlan)
            .where(MembershipPlan.level_id == level_id, MembershipPlan.is_del.is_(False))
            .values(is_del=True)
        )

    # 专享分组

    def list_level_group_ids(self, level_id: UUID) -> list[int]:
        """读取等级关联的专享分组标识。"""

        return list(
            self._session.scalars(
                select(MembershipLevelGroup.group_id)
                .where(MembershipLevelGroup.level_id == level_id)
                .order_by(MembershipLevelGroup.group_id)
            )
        )

    def list_groups_by_level_ids(self, level_ids: set[UUID]) -> list[tuple[UUID, TokenGroup]]:
        """批量读取等级关联的未删除分组。"""

        if not level_ids:
            return []
        return list(
            self._session.execute(
                select(MembershipLevelGroup.level_id, TokenGroup)
                .join(TokenGroup, TokenGroup.id == MembershipLevelGroup.group_id)
                .where(MembershipLevelGroup.level_id.in_(level_ids), TokenGroup.is_del.is_(False))
                .order_by(TokenGroup.id)
            ).all()
        )

    def replace_level_groups(self, level_id: UUID, group_ids: list[int]) -> None:
        """整体替换等级专享分组，保留逻辑删除历史。"""

        existing = list(
            self._session.scalars(
                select(MembershipLevelGroup)
                .where(MembershipLevelGroup.level_id == level_id)
                .execution_options(include_deleted=True)
            )
        )
        relations = {item.group_id: item for item in existing}
        self._session.execute(
            update(MembershipLevelGroup)
            .where(MembershipLevelGroup.level_id == level_id, MembershipLevelGroup.is_del.is_(False))
            .values(is_del=True)
        )
        for group_id in group_ids:
            relation = relations.get(group_id)
            if relation is None:
                self._session.add(MembershipLevelGroup(level_id=level_id, group_id=group_id))
            else:
                relation.is_del = False
        self._session.flush()

    def list_token_groups(self, group_ids: set[int]) -> list[TokenGroup]:
        """批量读取未删除的 Token 分组。"""

        if not group_ids:
            return []
        return list(self._session.scalars(select(TokenGroup).where(TokenGroup.id.in_(group_ids))))

    # 用户会员

    def get_user_membership(self, user_id: UUID) -> UserMembership | None:
        """读取用户会员行。"""

        return self._session.scalar(select(UserMembership).where(UserMembership.user_id == user_id))

    def get_user_membership_for_update(self, user_id: UUID) -> UserMembership | None:
        """锁定并读取用户会员行；不存在时锁定用户行以串行化首次开通。"""

        membership = self._session.scalar(
            select(UserMembership).where(UserMembership.user_id == user_id).with_for_update()
        )
        if membership is None:
            self._session.scalar(select(User.id).where(User.id == user_id).with_for_update())
        return membership

    def get_user(self, user_id: UUID) -> User | None:
        """读取未删除用户。"""

        return self._session.scalar(select(User).where(User.id == user_id))

    def add_user_membership(self, membership: UserMembership) -> UserMembership:
        """新增用户会员行。"""

        self._session.add(membership)
        self._session.flush()
        return membership

    def count_active_members_by_level(self, level_id: UUID, now: datetime) -> int:
        """统计指定等级下仍有效的会员数量。"""

        return (
            self._session.scalar(
                select(func.count())
                .select_from(UserMembership)
                .where(UserMembership.level_id == level_id, UserMembership.expires_at > now)
            )
            or 0
        )

    def list_user_memberships_page(
        self,
        *,
        user_id: UUID | None,
        level_id: UUID | None,
        is_active: bool | None,
        now: datetime,
        page: int,
        page_size: int,
    ) -> tuple[int, list[UserMembership]]:
        """按筛选条件分页读取用户会员及总数。"""

        conditions = []
        if user_id is not None:
            conditions.append(UserMembership.user_id == user_id)
        if level_id is not None:
            conditions.append(UserMembership.level_id == level_id)
        if is_active is True:
            conditions.append(UserMembership.expires_at > now)
        elif is_active is False:
            conditions.append(UserMembership.expires_at <= now)
        total = self._session.scalar(select(func.count()).select_from(UserMembership).where(*conditions)) or 0
        items = list(
            self._session.scalars(
                select(UserMembership)
                .where(*conditions)
                .order_by(UserMembership.updated_at.desc(), UserMembership.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items

    # 流水

    def add_record(self, record: MembershipRecord) -> MembershipRecord:
        """新增会员流水并刷新主键。"""

        self._session.add(record)
        self._session.flush()
        return record

    def get_record_by_order_id(self, order_id: UUID) -> MembershipRecord | None:
        """按来源订单读取会员流水，用于结算幂等。"""

        return self._session.scalar(select(MembershipRecord).where(MembershipRecord.recharge_order_id == order_id))

    def list_records_by_order_ids(self, order_ids: set[UUID]) -> list[MembershipRecord]:
        """按来源订单批量读取会员流水，用于支付流水展示。"""

        if not order_ids:
            return []
        return list(
            self._session.scalars(select(MembershipRecord).where(MembershipRecord.recharge_order_id.in_(order_ids)))
        )

    def list_records_page(
        self, *, user_id: UUID | None, page: int, page_size: int
    ) -> tuple[int, list[MembershipRecord]]:
        """按创建时间倒序分页读取会员流水及总数。"""

        conditions = [] if user_id is None else [MembershipRecord.user_id == user_id]
        total = self._session.scalar(select(func.count()).select_from(MembershipRecord).where(*conditions)) or 0
        items = list(
            self._session.scalars(
                select(MembershipRecord)
                .where(*conditions)
                .order_by(MembershipRecord.created_at.desc(), MembershipRecord.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return total, items
