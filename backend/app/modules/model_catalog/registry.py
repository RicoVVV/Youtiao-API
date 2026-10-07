"""内置模型价格目录的匹配入口。

目录只按模型名做精确匹配，未命中时按名称前缀推断厂商并回退到该厂商的默认文本模板；
两者都不成立时返回未匹配结果，由调用方要求管理员显式指定模板。
"""

from dataclasses import dataclass

from app.modules.model_catalog.entries import CATALOG_ENTRIES, ModelPricingEntry
from app.modules.model_catalog.matching import match_fallback, normalize_model_name

MATCH_EXACT = "exact"
MATCH_PROVIDER_FALLBACK = "provider_fallback"
MATCH_NONE = "none"


@dataclass(frozen=True)
class CatalogMatch:
    """一次模型名匹配的结果。

    ``entry`` 仅在精确命中时非空；``template_id`` 与 ``model_type`` 在精确命中与厂商回退
    时均有值，未匹配时为空。
    """

    model_name: str
    normalized_name: str
    match_type: str
    entry: ModelPricingEntry | None = None
    template_id: str | None = None
    model_type: str | None = None

    @property
    def matched(self) -> bool:
        return self.match_type == MATCH_EXACT


class ModelCatalog:
    """按模型名检索内置价格条目的只读目录。"""

    def __init__(self, entries: tuple[ModelPricingEntry, ...]) -> None:
        self._entries = entries
        self._entries_by_name: dict[str, ModelPricingEntry] = {}
        for entry in self._entries:
            for name in entry.search_names():
                # 同一归一化名称被多个条目登记时以先声明者为准，保证匹配结果稳定。
                self._entries_by_name.setdefault(normalize_model_name(name), entry)

    def match(self, model_name: str) -> CatalogMatch:
        """按模型名匹配目录条目，未命中时回退到厂商默认模板。"""

        normalized_name = normalize_model_name(model_name)
        entry = self._entries_by_name.get(normalized_name)
        if entry is not None:
            return CatalogMatch(
                model_name=model_name,
                normalized_name=normalized_name,
                match_type=MATCH_EXACT,
                entry=entry,
                template_id=entry.template_id,
                model_type=entry.model_type,
            )
        fallback = match_fallback(normalized_name)
        if fallback is not None:
            fallback_template_id, fallback_model_type = fallback
            return CatalogMatch(
                model_name=model_name,
                normalized_name=normalized_name,
                match_type=MATCH_PROVIDER_FALLBACK,
                template_id=fallback_template_id,
                model_type=fallback_model_type,
            )
        return CatalogMatch(model_name=model_name, normalized_name=normalized_name, match_type=MATCH_NONE)


def build_default_model_catalog() -> ModelCatalog:
    """构造内置价格目录，供运行时依赖组合根缓存复用。"""

    return ModelCatalog(CATALOG_ENTRIES)
