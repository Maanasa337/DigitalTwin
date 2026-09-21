from typing import Literal

from pydantic import BaseModel, Field

from app.common.schemas import ORMModel


class ScenarioOut(ORMModel):
    code: str
    name: str
    description: str | None


class ScenarioStart(BaseModel):
    scenario_code: str


class FaultInjection(BaseModel):
    asset: str
    failure_mode: str
    mode: Literal["sudden", "gradual"] = "gradual"
    severity: float = Field(0.5, ge=0, le=1)
    metric: str | None = None
    duration_s: float | None = Field(None, gt=0)


class TimeScale(BaseModel):
    factor: float = Field(ge=1, le=1000)


class ResetRequest(BaseModel):
    component_code: str | None = None


class ExportRequest(BaseModel):
    scenario_code: str | None = None
    hours: float = Field(gt=0, le=168)
    sample_period_s: float = Field(10, gt=0, le=3600)
    seed: int | None = None
