from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from app.core.i18n import translate
from app.modules.providers.logos import provider_logo_url


@dataclass(frozen=True)
class ProviderTemplate:
    template_id: str
    provider_type: str
    label: str
    model_type: str
    summary: str
    tags: list[str]
    input_schema: dict[str, Any]
    example: dict[str, Any]
    provider_id: str | None = None
    provider_name: str | None = None
    """面向用户公开的供应商归属：``provider_id`` 为稳定标识，``provider_name`` 为展示名称。

    两者均为空表示该模板没有明确的供应商；模型广场不会为其生成供应商筛选标签。
    """
    material_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    derived_pricing_fields: list[dict[str, str]] = field(default_factory=list)
    default_pricing_rules: list[dict[str, Any]] = field(default_factory=list)
    provider_config: dict[str, Any] = field(default_factory=dict)
    """声明参与素材归一化与计量的输入字段。

    键为输入契约中的字段名，值为 ``{"categories": [...], "multiple": bool}``；``categories`` 是该
    字段允许的素材类别（``image``/``video``/``audio``），``multiple`` 表示字段是否为数组。

    ``default_pricing_rules`` 是按尺寸档位等条件预设的完整定价规则
    （``name``/``priority``/``conditions``/``items``），条目形状与管理员定价接口一致，供新建模型播种。
    """

    def summary_data(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "provider_type": self.provider_type,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "label": self.label,
            "model_type": self.model_type,
            "summary": self.summary,
            "tags": deepcopy(self.tags),
        }

    def detail(self) -> dict[str, Any]:
        return {
            **self.summary_data(),
            "input_schema": deepcopy(self.input_schema),
            "material_fields": deepcopy(self.material_fields),
            "derived_pricing_fields": deepcopy(self.derived_pricing_fields),
            "default_pricing_rules": deepcopy(self.default_pricing_rules),
            "example": deepcopy(self.example),
        }

    def internal_data(self) -> dict[str, Any]:
        return {
            **self.detail(),
            "provider_config": deepcopy(self.provider_config),
        }

    def summary_view(self, locale: str) -> dict[str, Any]:
        """按语言投影列表展示字段。

        ``label``、``summary``、``tags``、``provider_name`` 为展示文案，随语言切换；
        ``template_id``、``provider_type``、``provider_id``、``model_type`` 是稳定标识，始终原样返回。
        ``provider_logo_url`` 由供应商归属推导，与请求语言无关，未登记图标的供应商返回空值。
        """

        return {
            "template_id": self.template_id,
            "provider_type": self.provider_type,
            "provider_id": self.provider_id,
            "provider_name": translate(self.provider_name, locale) if self.provider_name else None,
            "provider_logo_url": provider_logo_url(self.provider_id),
            "label": translate(self.label, locale),
            "model_type": self.model_type,
            "summary": translate(self.summary, locale),
            "tags": [translate(tag, locale) for tag in self.tags],
        }

    def detail_view(self, locale: str) -> dict[str, Any]:
        """在列表展示字段基础上追加公开契约与按语言投影的调用示例。

        默认定价规则属于配置数据，管理台需要原文回显与编辑，因此保持模板原文返回。
        """

        return {
            **self.summary_view(locale),
            "input_schema": deepcopy(self.input_schema),
            "material_fields": deepcopy(self.material_fields),
            "derived_pricing_fields": deepcopy(self.derived_pricing_fields),
            "default_pricing_rules": deepcopy(self.default_pricing_rules),
            "example": _localize_text(self.example, locale),
        }


def _localize_text(value: Any, locale: str) -> Any:
    """递归翻译结构内的字符串，未收录的字段名与枚举值原样保留。"""

    if isinstance(value, str):
        return translate(value, locale)
    if isinstance(value, list):
        return [_localize_text(item, locale) for item in value]
    if isinstance(value, dict):
        return {key: _localize_text(item, locale) for key, item in value.items()}
    return value


class ProviderTemplateRegistry:
    def __init__(self, templates: list[ProviderTemplate]) -> None:
        self._templates = {template.template_id: template for template in templates}

    def list(self) -> list[dict[str, str]]:
        return [template.summary_data() for template in self._templates.values()]

    def get(self, template_id: str) -> dict[str, Any] | None:
        template = self._templates.get(template_id)
        return template.detail() if template is not None else None

    def get_internal(self, template_id: str) -> dict[str, Any] | None:
        template = self._templates.get(template_id)
        return template.internal_data() if template is not None else None

    def list_views(self, locale: str) -> list[dict[str, Any]]:
        """按语言返回全部模板的展示数据。"""

        return [template.summary_view(locale) for template in self._templates.values()]

    def get_view(self, template_id: str, locale: str) -> dict[str, Any] | None:
        """按语言返回单个模板的展示数据，模板不存在时返回空值。"""

        template = self._templates.get(template_id)
        return template.detail_view(locale) if template is not None else None
