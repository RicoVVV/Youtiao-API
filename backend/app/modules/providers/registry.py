"""Provider 注册表，隔离模型协议名称与可按冻结配置创建的适配器构造器。

注册表只登记 Provider 协议的无状态原型；渠道实例由工厂传入冻结的连接信息与凭据引用创建或缓存。
"""

from collections.abc import Callable

from app.modules.providers.contracts import ProviderInstanceConfig, VideoProvider

ProviderBuilder = Callable[[ProviderInstanceConfig], VideoProvider]


class ProviderRegistry:
    """按稳定名称管理已注册的视频 Provider。

    初始化时按 Provider 的 ``name`` 建立索引，重复名称以后出现的实例为准，因此启动配置应保证名称唯一。
    """

    def __init__(self, builders: dict[str, ProviderBuilder]) -> None:
        """使用按 Provider 名称索引的实例构造器初始化注册表。

        Args:
            builders: 每个 Provider 类型对应的冻结实例构造器，不得在构造器外泄露凭据。
        """

        self._builders = dict(builders)

    def create(self, config: ProviderInstanceConfig) -> VideoProvider:
        """按冻结渠道参数创建 Provider 实例。

        Args:
            config: 创建任务时冻结的 Provider、凭据引用及非敏感运行选项。

        Returns:
            仅服务本次冻结配置的 Provider 适配器。

        Raises:
            KeyError: Provider 类型未注册，调用方应将其视为不可恢复的配置不一致。
        """

        return self._builders[config.provider_type](config)
