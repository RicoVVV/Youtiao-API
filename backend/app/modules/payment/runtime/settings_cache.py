"""支付配置进程缓存，为下单、回调和展示接口提供原子且只读的运行时快照。"""

from threading import RLock

from app.modules.payment.domain.config import PaymentRuntimeConfig


class PaymentSettingsRuntime:
    """线程安全地保存当前支付配置快照。"""

    def __init__(self) -> None:
        """创建空缓存容器，应用启动成功加载配置后才会发布快照。

        作用：初始化保护快照替换的锁和空配置状态。
        使用位置：模块级 payment_settings_runtime 创建时调用。
        传入参数：无。
        返回参数：无。
        """
        self._lock = RLock()
        self._config: PaymentRuntimeConfig | None = None

    def get(self) -> PaymentRuntimeConfig | None:
        """返回当前不可修改的支付快照。

        作用：让请求只读取内存快照而不直接访问配置表。
        使用位置：支付应用服务执行展示、下单和回调时调用。
        传入参数：无。
        返回参数：未发布配置时返回 None，否则返回独立只读快照。
        """
        with self._lock:
            return PaymentRuntimeConfig.freeze(self._config) if self._config else None

    def replace(self, config: PaymentRuntimeConfig) -> None:
        """原子发布一份已验证的支付快照。

        作用：数据库提交成功后一次替换全部 Provider 配置，避免半成品状态。
        使用位置：PaymentSettingsService 更新配置和启动刷新完成后调用。
        传入参数：config 为已通过校验的完整支付配置。
        返回参数：无。
        """
        with self._lock:
            self._config = PaymentRuntimeConfig.freeze(config)

    def has_config(self) -> bool:
        """判断是否已发布有效快照，供启动流程判断支付配置状态。

        作用：提供不暴露配置内容的缓存状态检查。
        使用位置：启动和健康检查相关流程调用。
        传入参数：无。
        返回参数：已发布快照时返回 True，否则返回 False。
        """
        with self._lock:
            return self._config is not None
