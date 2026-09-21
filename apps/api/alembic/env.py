from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import get_settings
from app.core.db import Base

config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Hide the indexes Timescale creates for itself from autogenerate and `alembic check`.

    `create_hypertable` adds a `<table>_time_idx` to every hypertable. It exists in the database and
    can never exist on an ORM model, so without this filter autogenerate proposes dropping six
    indexes on every run and `alembic check` can never pass.
    """
    return not (type_ == "index" and reflected and name and name.endswith("_time_idx"))


def configure(**kwargs: Any) -> None:
    context.configure(target_metadata=target_metadata, include_object=include_object, **kwargs)


def run_migrations_offline() -> None:
    configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection") or engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    else:
        configure(connection=connectable)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
