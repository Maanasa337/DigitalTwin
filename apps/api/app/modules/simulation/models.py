from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, PKMixin, TimestampMixin


class Scenario(TimestampMixin, Base):
    __tablename__ = "scenarios"

    code: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str | None]
    yaml: Mapped[str]


class ScenarioRun(PKMixin, Base):
    __tablename__ = "scenario_runs"

    scenario_code: Mapped[str | None] = mapped_column(ForeignKey("scenarios.code"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]
    time_scale: Mapped[float] = mapped_column(server_default="1")
    seed: Mapped[int | None]
    export_uri: Mapped[str | None]
