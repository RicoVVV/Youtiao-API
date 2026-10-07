"""运行时依赖组合根，集中创建 Provider 等可替换基础设施。"""

from functools import lru_cache

from app.modules.model_catalog.registry import ModelCatalog, build_default_model_catalog
from app.modules.providers.anthropic.adapter import AnthropicProvider
from app.modules.providers.anthropic.templates import ANTHROPIC_MESSAGES_DEFAULT_TEMPLATE
from app.modules.providers.contracts import ProviderInstanceConfig
from app.modules.providers.dashscope.adapter import DashScopeProvider
from app.modules.providers.dashscope.templates import DASHSCOPE_DEFAULT_TEMPLATE, DASHSCOPE_VIDEO_DEFAULT_TEMPLATE
from app.modules.providers.doubao_seed.adapter import DoubaoSeedProvider
from app.modules.providers.doubao_seed.templates import DOUBAO_SEED_DEFAULT_TEMPLATE
from app.modules.providers.factory import ChannelProviderFactory
from app.modules.providers.fal.adapter import FalVideoProvider
from app.modules.providers.fal.templates import (
    FAL_MINIMAX_H3_MAX_IMAGE_TO_VIDEO_TEMPLATE,
    FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE,
    FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE,
)
from app.modules.providers.gemini.adapter import GeminiProvider
from app.modules.providers.gemini.templates import (
    GEMINI_IMAGE_DEFAULT_TEMPLATE,
    GEMINI_TEXT_DEFAULT_TEMPLATE,
)
from app.modules.providers.hook_minimax_h3.adapter import H3VideoProvider
from app.modules.providers.hook_minimax_h3.templates import MINIMAX_H3_DEFAULT_TEMPLATE
from app.modules.providers.minimax_h3_official.adapter import MiniMaxH3OfficialProvider
from app.modules.providers.minimax_h3_official.templates import MINIMAX_H3_OFFICIAL_DEFAULT_TEMPLATE
from app.modules.providers.openai_compatible.adapter import OpenAICompatibleProvider
from app.modules.providers.openai_compatible.templates import (
    OPENAI_IMAGE_DEFAULT_TEMPLATE,
    OPENAI_TEXT_DEFAULT_TEMPLATE,
    OPENAI_VIDEO_DEFAULT_TEMPLATE,
)
from app.modules.providers.registry import ProviderRegistry
from app.modules.providers.templates import ProviderTemplateRegistry


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    """创建进程内唯一的 Provider 注册表。

    返回值：按稳定 Provider 类型检索适配器的注册表。
    副作用：首次调用时从运行配置构造 Provider，密钥不被持久化。
    """

    def build_h3(config: ProviderInstanceConfig) -> H3VideoProvider:
        """使用任务冻结的渠道地址与凭据构造 H3 Provider。"""

        if config.api_key is None:
            raise ValueError("H3 渠道 API Key 未配置")
        return H3VideoProvider(
            base_url=config.base_url,
            api_key=config.api_key,
        )

    def build_openai_compatible(config: ProviderInstanceConfig) -> OpenAICompatibleProvider:
        """使用任务冻结的渠道地址与凭据构造 OpenAI 兼容生成 Provider。"""

        return OpenAICompatibleProvider(
            base_url=config.base_url,
            api_key=config.api_key,
        )

    def build_anthropic(config: ProviderInstanceConfig) -> AnthropicProvider:
        return AnthropicProvider(base_url=config.base_url, api_key=config.api_key)

    def build_gemini(config: ProviderInstanceConfig) -> GeminiProvider:
        return GeminiProvider(base_url=config.base_url, api_key=config.api_key)

    def build_dashscope(config: ProviderInstanceConfig) -> DashScopeProvider:
        """构造千问原生 Generation Provider，端点由公开请求路径决定。"""

        return DashScopeProvider(base_url=config.base_url, api_key=config.api_key)

    def build_doubao_seed(config: ProviderInstanceConfig) -> DoubaoSeedProvider:
        """构造火山方舟 Responses Provider。"""

        return DoubaoSeedProvider(base_url=config.base_url, api_key=config.api_key)

    def build_fal(config: ProviderInstanceConfig) -> FalVideoProvider:
        return FalVideoProvider(base_url=config.base_url, api_key=config.api_key, provider_config=config.config)

    def build_minimax_h3_official(config: ProviderInstanceConfig) -> MiniMaxH3OfficialProvider:
        return MiniMaxH3OfficialProvider(base_url=config.base_url, api_key=config.api_key)

    return ProviderRegistry(
        {
            "anthropic": build_anthropic,
            "dashscope": build_dashscope,
            "doubao_seed": build_doubao_seed,
            "gemini": build_gemini,
            "minimax_h3": build_h3,
            "openai_compatible": build_openai_compatible,
            "fal": build_fal,
            "minimax_h3_official": build_minimax_h3_official,
        }
    )


@lru_cache
def get_provider_template_registry() -> ProviderTemplateRegistry:
    return ProviderTemplateRegistry(
        [
            MINIMAX_H3_DEFAULT_TEMPLATE,
            MINIMAX_H3_OFFICIAL_DEFAULT_TEMPLATE,
            OPENAI_IMAGE_DEFAULT_TEMPLATE,
            OPENAI_TEXT_DEFAULT_TEMPLATE,
            OPENAI_VIDEO_DEFAULT_TEMPLATE,
            GEMINI_TEXT_DEFAULT_TEMPLATE,
            GEMINI_IMAGE_DEFAULT_TEMPLATE,
            ANTHROPIC_MESSAGES_DEFAULT_TEMPLATE,
            DASHSCOPE_DEFAULT_TEMPLATE,
            DASHSCOPE_VIDEO_DEFAULT_TEMPLATE,
            DOUBAO_SEED_DEFAULT_TEMPLATE,
            FAL_MINIMAX_H3_MAX_TEXT_TO_VIDEO_TEMPLATE,
            FAL_MINIMAX_H3_MAX_REFERENCE_TO_VIDEO_TEMPLATE,
            FAL_MINIMAX_H3_MAX_IMAGE_TO_VIDEO_TEMPLATE,
        ]
    )


@lru_cache
def get_model_catalog() -> ModelCatalog:
    """创建进程内唯一的模型价格目录。

    返回值：按模型名匹配厂商模板与公开定价的只读目录。
    副作用：首次调用时构造目录索引，不读取数据库或外部服务。
    """

    return build_default_model_catalog()


@lru_cache
def get_channel_provider_factory() -> ChannelProviderFactory:
    """创建进程内共享的渠道实例工厂。

    返回值：只按任务冻结 Provider 标识返回适配器的工厂。
    副作用：首次调用复用已初始化的 Provider 注册表，不读取或持久化认证信息。
    """

    return ChannelProviderFactory(get_provider_registry())
