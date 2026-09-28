import os
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from app.bootstrap.model_registry import load_models
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

config = context.config
load_models()
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL 环境变量未设置")
config.set_main_option("sqlalchemy.url", database_url)
if config.config_file_name is not None and config.get_section("loggers") is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def ensure_version_table(connection: sa.Connection) -> None:
    """初始化并扩容 Alembic 版本表，确保迁移标识可使用最多 128 个字符。"""

    connection.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(128) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
            """
        )
    )
    connection.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"))
    connection.commit()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        ensure_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
