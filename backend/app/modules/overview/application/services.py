"""用户概览聚合应用服务，编排用量、余额、公告与站点信息读取。"""

from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.modules.message.application.services import MessageService
from app.modules.site_info.application.services import SiteInfoApplicationService
from app.modules.usage.application.statistics_services import UsageStatisticsApplicationService
from app.modules.wallet.application.services import WalletApplicationService

USAGE_FIELDS = (
    "total_count",
    "settled_amount",
    "success_rate",
    "total_tokens",
    "average_rpm",
    "average_tpm",
)


class OverviewApplicationService:
    """聚合仪表板所需的用量、余额、公告与站点信息，只做编排不写查询。"""

    def __init__(self, session: Session) -> None:
        """绑定请求会话并初始化各领域服务。"""

        self._usage = UsageStatisticsApplicationService(session)
        self._wallet = WalletApplicationService(session)
        self._messages = MessageService(session)
        self._site_infos = SiteInfoApplicationService(session)

    def user_overview(self, *, user_id: UUID, message_page: int, message_page_size: int) -> dict[str, Any]:
        """返回当前用户的仪表板概览数据。"""

        usage = self._usage.overview(filters={"user_id": user_id}, range_name="today", start_at=None, end_at=None)
        return {
            "usage": {field: usage[field] for field in USAGE_FIELDS},
            "wallet": self._wallet.get_balance_summary(user_id),
            "messages": self._messages.list_page(
                user_id=user_id,
                message_type=None,
                unread_only=False,
                page=message_page,
                page_size=message_page_size,
            ),
            "site_infos": self._site_infos.list_active_views(),
        }
