"""渠道 Provider 实例工厂。"""

from copy import deepcopy
from typing import Any

from app.modules.providers.contracts import (
    GenerationProvider,
    ProviderError,
    ProviderInstanceConfig,
    VideoProvider,
)
from app.modules.providers.registry import ProviderRegistry


class ChannelProviderFactory:
    """根据模型协议与冻结渠道连接配置取得唯一的可执行 Provider 适配器。"""

    def __init__(self, registry: ProviderRegistry) -> None:
        """使用进程启动时完成初始化的注册表创建渠道实例工厂。"""

        self._registry = registry

    def get_frozen_provider(self, snapshot: dict[str, Any], *, provider_type: str, api_key: str) -> VideoProvider:
        """按模型协议与任务渠道快照构造或复用视频 Provider，缺失字段或未注册类型均不可重试。

        快照必须包含 ``route_id``、``base_url`` 与 ``config``；API Key 由 Worker 依据任务冻结的渠道
        从受控表读取，只传递给部署内构造器，任何异常均规范为不重试的 ``ProviderError``。
        """

        return self._build(snapshot, provider_type=provider_type, api_key=api_key)

    def get_frozen_generation_provider(
        self, snapshot: dict[str, Any], *, provider_type: str, api_key: str
    ) -> GenerationProvider:
        """按模型协议和冻结渠道连接配置构造同步生成 Provider。"""

        return self._build(snapshot, provider_type=provider_type, api_key=api_key)

    def _build(self, snapshot: dict[str, Any], *, provider_type: str, api_key: str) -> Any:
        """校验冻结快照并创建 Provider，异常统一为不可重试的 ``ProviderError``。"""

        try:
            route_id = snapshot["route_id"]
            config = snapshot["config"]
            base_url = snapshot["base_url"]
            if (
                not isinstance(route_id, str)
                or not isinstance(provider_type, str)
                or not provider_type
                or not isinstance(config, dict)
                or not isinstance(base_url, str)
                or not isinstance(api_key, str)
                or not api_key
            ):
                raise ValueError("冻结渠道实例快照不合法")
            return self._registry.create(
                ProviderInstanceConfig(
                    provider_type=provider_type,
                    config=deepcopy(config),
                    base_url=base_url,
                    api_key=api_key,
                )
            )
        except ProviderError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("冻结渠道 Provider 不可用", code="unknown_provider", retryable=False) from exc
