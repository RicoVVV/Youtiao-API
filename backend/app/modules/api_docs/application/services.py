"""接口文档查询用例。

文档内容全部来自 Provider 模板与公开协议声明：模板随代码发布，实时投影即可保证文档与实现一致，
因此用例不读写数据库，也不缓存结果。

目录分四到五级：能力 → 模型族 → 条目 → 接口（→ 请求体参数形态）。条目下的接口来自协议声明，
接口的参数形态来自模板声明，详情接口把两者合并为自包含的接口文档，前端可只渲染到接口层，
也可继续下钻到形态层。
"""

from typing import Any

from app.bootstrap.container import get_provider_template_registry
from app.core.errors import NotFoundError
from app.core.i18n import get_locale, translate
from app.core.protocols import BEARER_API_KEY_AUTH, model_operations
from app.modules.api_docs.application.catalog import (
    CAPABILITY_NAMES,
    CAPABILITY_ORDER,
    DocumentedEntry,
    entries_of,
    family_display_name,
    find_entry,
)
from app.modules.api_docs.application.endpoints import DocumentedEndpoint, endpoint_doc
from app.modules.api_docs.application.reference import (
    error_reference,
    material_notes,
    stream_notes,
    video_status_reference,
)
from app.modules.providers.logos import provider_logo_url
from app.modules.providers.templates import ProviderTemplateRegistry


class ApiDocsApplicationService:
    """对外调用文档的只读用例。"""

    def list_catalog(self, *, model_type: str | None = None) -> dict[str, Any]:
        """返回按能力与模型族分组的目录，供文档页导航渲染。

        参数 ``model_type`` 非空时只返回该能力的目录；条目下的 ``endpoints`` 是接口级节点，
        ``endpoints[].forms`` 是该接口下的请求体参数形态。模板全部缺失的条目会被跳过，
        避免目录出现点不开的空页。
        """

        locale = get_locale()
        registry = get_provider_template_registry()
        capabilities: list[dict[str, Any]] = []
        for capability in CAPABILITY_ORDER:
            if model_type is not None and model_type != capability:
                continue
            families: dict[str, dict[str, Any]] = {}
            for entry in entries_of(capability):
                view = self._first_view(registry, entry, locale)
                if view is None:
                    continue
                family = families.setdefault(
                    entry.family_id,
                    {**self._family_view(entry.family_id, locale), "items": []},
                )
                family["items"].append(
                    {
                        "slug": entry.slug,
                        "name": translate(entry.name, locale),
                        "summary": translate(entry.summary, locale) if entry.summary else view["summary"],
                        "tags": view["tags"],
                        "endpoints": self._endpoint_nodes(registry, entry, locale),
                    }
                )
            capabilities.append(
                {
                    "model_type": capability,
                    "name": translate(CAPABILITY_NAMES[capability], locale),
                    "families": list(families.values()),
                }
            )
        return {"auth": dict(BEARER_API_KEY_AUTH), "capabilities": capabilities}

    def get_entry(self, *, slug: str) -> dict[str, Any]:
        """返回单个条目的完整调用文档。

        参数 ``slug`` 为目录中的条目标识，未登记时抛出未找到异常。返回值中每个接口自包含方法、
        路径、参数与响应说明，创建类接口还带有逐调用形态的请求体契约；错误码与视频任务状态说明
        属于跨接口的公共内容，放在条目级返回。
        """

        locale = get_locale()
        entry = find_entry(slug)
        if entry is None:
            raise NotFoundError("接口文档条目不存在")
        registry = get_provider_template_registry()
        forms = self._form_payloads(registry, entry, locale)
        first_view = self._first_view(registry, entry, locale)
        endpoints = self._endpoints(entry, forms, locale)
        return {
            "slug": entry.slug,
            "name": translate(entry.name, locale),
            "model_type": entry.model_type,
            "capability_name": translate(CAPABILITY_NAMES[entry.model_type], locale),
            "summary": translate(entry.summary, locale) if entry.summary else (forms[0]["summary"] if forms else None),
            "tags": first_view["tags"] if first_view is not None else [],
            "family": self._family_view(entry.family_id, locale),
            "auth": dict(BEARER_API_KEY_AUTH),
            "endpoints": endpoints,
            "error_reference": error_reference([endpoint["protocol_id"] for endpoint in endpoints], locale),
            "status_reference": video_status_reference(locale) if entry.model_type == "video" else None,
        }

    def _endpoints(self, entry: DocumentedEntry, forms: list[dict[str, Any]], locale: str) -> list[dict[str, Any]]:
        """把协议端点与调用形态合并为自包含的接口文档。"""

        endpoints: list[dict[str, Any]] = []
        for operation in self._operations(entry):
            doc = endpoint_doc(operation["method"], operation["path"])
            stream = operation.get("stream")
            endpoints.append(
                {
                    "operation_id": doc.operation_id if doc is not None else None,
                    "name": translate(doc.name, locale) if doc is not None else operation["path"],
                    "summary": translate(doc.summary, locale) if doc is not None else None,
                    "protocol_id": operation["protocol_id"],
                    "method": operation["method"],
                    "path": operation["path"],
                    "content_type": operation["content_type"],
                    "stream": stream,
                    "path_params": self._localized_items(doc.path_params if doc is not None else (), locale),
                    "query_params": self._localized_items(doc.query_params if doc is not None else (), locale),
                    "responses": self._localized_items(doc.responses if doc is not None else (), locale),
                    "notes": stream_notes(stream, locale),
                    "forms": forms if doc is not None and doc.request_body else [],
                }
            )
        return endpoints

    def _endpoint_nodes(
        self, registry: ProviderTemplateRegistry, entry: DocumentedEntry, locale: str
    ) -> list[dict[str, Any]]:
        """返回条目下的接口级导航节点，只含标识与展示字段，契约细节由详情接口给出。

        创建类接口有多个调用形态时按形态平铺成同级节点（例如文生、图生、参考生各自一个节点，
        带的方法徽标都取该接口自身的方法），形态唯一时只给出接口本身，避免出现只有一个子节点的多余层级。
        节点的唯一标识是 ``operation_id`` 与 ``template_id`` 的组合。
        """

        forms = self._form_titles(registry, entry, locale)
        nodes: list[dict[str, Any]] = []
        for operation in self._operations(entry):
            doc: DocumentedEndpoint | None = endpoint_doc(operation["method"], operation["path"])
            name = translate(doc.name, locale) if doc is not None else operation["path"]
            request_body = doc is not None and doc.request_body
            leaves = forms if request_body and len(forms) > 1 else [{"template_id": None, "title": name}]
            nodes.extend(
                {
                    "operation_id": doc.operation_id if doc is not None else None,
                    "name": leaf["title"],
                    "method": operation["method"],
                    "path": operation["path"],
                    "template_id": leaf["template_id"],
                }
                for leaf in leaves
            )
        return nodes

    @staticmethod
    def _form_payloads(registry: ProviderTemplateRegistry, entry: DocumentedEntry, locale: str) -> list[dict[str, Any]]:
        """返回条目下各调用形态的完整请求体契约。"""

        payloads: list[dict[str, Any]] = []
        for template_id in entry.template_ids:
            view = registry.get_view(template_id, locale)
            if view is None:
                continue
            payloads.append(
                {
                    "template_id": template_id,
                    "title": _form_title(entry, template_id, view, locale),
                    "summary": view["summary"],
                    "parameters": view["input_schema"],
                    "material_fields": view["material_fields"],
                    "example": {"model": translate(entry.name, locale), **view["example"]},
                    "notes": material_notes(view["material_fields"], locale),
                }
            )
        return payloads

    @staticmethod
    def _form_titles(registry: ProviderTemplateRegistry, entry: DocumentedEntry, locale: str) -> list[dict[str, Any]]:
        """返回条目下各调用形态的标识与展示名，供目录节点下钻使用。"""

        titles: list[dict[str, Any]] = []
        for template_id in entry.template_ids:
            view = registry.get_view(template_id, locale)
            if view is not None:
                titles.append({"template_id": template_id, "title": _form_title(entry, template_id, view, locale)})
        return titles

    @staticmethod
    def _localized_items(items: tuple[dict[str, Any], ...], locale: str) -> list[dict[str, Any]]:
        """翻译参数与响应说明中的 ``description``，其余字段保持稳定标识。"""

        return [{**item, "description": translate(item["description"], locale)} for item in items]

    @staticmethod
    def _operations(entry: DocumentedEntry) -> list[dict[str, Any]]:
        """聚合条目下全部模板的端点并按方法与路径去重，保持声明顺序。

        同一能力下多个调用形态共用同一批端点（例如视频的创建、查询与下载），去重后作为条目的接口清单。
        """

        operations: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for template_id in entry.template_ids:
            for operation in model_operations(template_id=template_id, model_type=entry.model_type):
                key = (operation["method"], operation["path"])
                if key in seen:
                    continue
                seen.add(key)
                operations.append(operation)
        return operations

    @staticmethod
    def _first_view(registry: ProviderTemplateRegistry, entry: DocumentedEntry, locale: str) -> dict[str, Any] | None:
        """返回条目首个可读取到模板的展示投影，全部缺失时返回空值。"""

        for template_id in entry.template_ids:
            view = registry.get_view(template_id, locale)
            if view is not None:
                return view
        return None

    @staticmethod
    def _family_view(family_id: str, locale: str) -> dict[str, Any]:
        """把模型族投影为分组节点。

        族图标按族标识取供应商图标：族标识即对外品牌标识，同族的多个渠道实现共用一份图标，
        未登记图标时为空值。
        """

        return {
            "family_id": family_id,
            "family_name": translate(family_display_name(family_id), locale),
            "provider_logo_url": provider_logo_url(family_id),
        }


def _form_title(entry: DocumentedEntry, template_id: str, view: dict[str, Any], locale: str) -> str:
    """返回调用形态的对外展示名；条目已声明时覆盖模板 ``label``。

    模板 ``label`` 会带上渠道与实现细节，目录节点与正文标题都应以条目声明的形态名为准。
    """

    declared = entry.form_names.get(template_id)
    return translate(declared, locale) if declared else view["label"]
