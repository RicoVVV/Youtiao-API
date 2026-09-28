"""本地开发启动编排，仅负责执行数据库迁移。"""

import os
import subprocess
import sys
from pathlib import Path

from app.core.config import get_settings

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG = _BACKEND_ROOT / "alembic.ini"


def run_database_migrations() -> None:
    """执行当前数据库的 Alembic 迁移。

    异常：迁移命令失败时抛出 CalledProcessError 并阻止 API 启动。
    副作用：更新当前 DATABASE_URL 指向数据库的表结构与迁移版本。
    """

    environment = os.environ.copy()
    # Alembic 子进程不读取 Pydantic 的 .env 配置，显式传递已校验的连接串以保持 IDEA 启动一致。
    environment["DATABASE_URL"] = get_settings().database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_CONFIG), "upgrade", "head"],
        check=True,
        env=environment,
        cwd=_BACKEND_ROOT,
    )
