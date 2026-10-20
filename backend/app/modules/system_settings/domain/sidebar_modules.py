"""控制台侧边栏模块目录与可见性规则。

本模块只承载纯数据结构与判定逻辑，不依赖框架、数据库或 HTTP。
目录是全站唯一事实来源：新增侧边栏模块必须在此登记，否则既无法配置可见性，也无法被拦截依赖引用。
模块 key 与前端路由段一一对应（``/console/<key>``），显示名与描述由前端 i18n 负责。
"""

SIDEBAR_GROUPS: dict[str, tuple[str, ...]] = {
    "chat": ("playground", "canvas"),
    "general": ("usage", "monitoring", "api-keys", "usage-records"),
    "account": ("billing", "profile"),
}
"""分组 key → 该分组模块 key 顺序表。"""

GROUP_KEYS: tuple[str, ...] = tuple(SIDEBAR_GROUPS)
MODULE_KEYS: tuple[str, ...] = tuple(module for modules in SIDEBAR_GROUPS.values() for module in modules)
_MODULE_GROUPS: dict[str, str] = {module: group for group, modules in SIDEBAR_GROUPS.items() for module in modules}


def module_group(module_key: str) -> str | None:
    """返回模块所属分组；目录外的 key 返回 None。"""

    return _MODULE_GROUPS.get(module_key)


def normalize_visibility(visibility: dict | None) -> dict[str, dict[str, bool]]:
    """把覆盖表补全为按目录顺序、包含全部键的完整开关表。

    参数：visibility 为落库的覆盖表，可能只含被改动的键。
    返回值：``{"groups": {...}, "modules": {...}}``，缺失键补 ``True``（可见）。
    """

    raw = visibility if isinstance(visibility, dict) else {}
    groups = raw.get("groups") if isinstance(raw.get("groups"), dict) else {}
    modules = raw.get("modules") if isinstance(raw.get("modules"), dict) else {}
    return {
        "groups": {group: bool(groups.get(group, True)) for group in GROUP_KEYS},
        "modules": {module: bool(modules.get(module, True)) for module in MODULE_KEYS},
    }


def visible_modules(visibility: dict | None) -> list[str]:
    """返回生效可见的模块 key 列表，按目录顺序。

    参数：visibility 为落库的覆盖表。
    返回值：分组可见且模块开关为真的模块 key。分组关闭时其下模块全部不可见。
    """

    normalized = normalize_visibility(visibility)
    return [
        module
        for module in MODULE_KEYS
        if normalized["groups"][_MODULE_GROUPS[module]] and normalized["modules"][module]
    ]


def is_module_visible(visibility: dict | None, module_key: str) -> bool:
    """判断单个模块是否生效可见。

    参数：visibility 为落库的覆盖表，module_key 为待判定模块。
    返回值：分组可见且模块开关为真时为 True；目录外的 key 恒为 True，避免误伤未登记的既有能力。
    """

    group = _MODULE_GROUPS.get(module_key)
    if group is None:
        return True
    normalized = normalize_visibility(visibility)
    return normalized["groups"][group] and normalized["modules"][module_key]
