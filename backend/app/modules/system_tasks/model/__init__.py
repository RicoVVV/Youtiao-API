"""系统任务 ORM 模型统一导出，供跨模块关系加载使用。"""

from app.modules.system_tasks.model.system_task import SystemTask, SystemTaskStatus

__all__ = ["SystemTask", "SystemTaskStatus"]
