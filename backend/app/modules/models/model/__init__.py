"""公开模型目录 ORM 模型统一导出，供跨模块关系加载使用。"""

from app.modules.models.model.model import Model, ModelRoute

__all__ = ["Model", "ModelRoute"]
