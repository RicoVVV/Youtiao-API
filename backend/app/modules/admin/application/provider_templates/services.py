from typing import Any

from app.core.errors import NotFoundError
from app.core.i18n import get_locale
from app.modules.providers.templates import ProviderTemplateRegistry


class AdminProviderTemplateApplicationService:
    def __init__(self, registry: ProviderTemplateRegistry) -> None:
        self._registry = registry

    def list_templates(self) -> list[dict[str, str]]:
        return self._registry.list_views(get_locale())

    def get_template(self, template_id: str) -> dict[str, Any]:
        template = self._registry.get_view(template_id, get_locale())
        if template is None:
            raise NotFoundError("Provider 模板不存在")
        return template
