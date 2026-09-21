import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class RulOut(BaseModel):
    point: float | None = None
    low: float | None = None
    high: float | None = None
    unit: str | None = None


class TreeComponent(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    component_type: str
    health: float | None
    rul: RulOut | None


class TreeAsset(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    asset_type: str
    status: str
    fidelity_level: int
    health: float | None
    components: list[TreeComponent]


class TreeLine(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    health: float | None
    assets: list[TreeAsset]


class TreePlant(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    health: float | None
    lines: list[TreeLine]


class TwinTree(BaseModel):
    plants: list[TreePlant]


class TwinOut(BaseModel):
    code: str
    asset_id: uuid.UUID
    thing_id: str
    policy_id: str | None
    revision: int | None
    status: str
    fidelity_level: int
    health: float | None
    attributes: dict[str, Any]
    features: dict[str, Any]


class SetLoadParams(BaseModel):
    load_pct: float = Field(ge=0, le=110)


class SetSpeedParams(BaseModel):
    speed_pct: float = Field(ge=50, le=120)


class MaintenanceResetParams(BaseModel):
    component_code: str | None = None


class _Command(BaseModel):
    pin: str | None = Field(None, max_length=16)


class SetLoadCommand(_Command):
    command: Literal["set_load"]
    params: SetLoadParams


class SetSpeedCommand(_Command):
    command: Literal["set_speed"]
    params: SetSpeedParams


class MaintenanceResetCommand(_Command):
    command: Literal["maintenance_reset"]
    params: MaintenanceResetParams = Field(default_factory=MaintenanceResetParams)


CommandRequest = Annotated[SetLoadCommand | SetSpeedCommand | MaintenanceResetCommand, Field(discriminator="command")]


class CommandResult(BaseModel):
    command_id: str
    command: str
    status: Literal["accepted", "rejected"]
    error: str | None


# ── What-if (FR-DT-09) ────────────────────────────────────────────────


class WhatIfRequest(BaseModel):
    """A hypothetical operating point. Anything left unset stays at the twin's current value."""

    load_pct: float | None = Field(None, ge=0, le=200)
    speed_pct: float | None = Field(None, ge=0, le=200)
    ambient_c: float | None = Field(None, ge=-40, le=120)
    maintenance_in_h: float | None = Field(None, ge=0, le=8760)
    horizon_h: float = Field(168.0, gt=0, le=8760)
    trials: int = Field(500, ge=50, le=5000)


class WhatIfConditions(BaseModel):
    load_pct: float
    speed_pct: float
    ambient_c: float | None = None


class WhatIfDistribution(BaseModel):
    trials: int
    mean_h: float | None
    p10_h: float | None
    p50_h: float | None
    p90_h: float | None
    risk_within_horizon: float
    first_to_fail: dict[str, float]


class WhatIfEnergy(BaseModel):
    baseline_kwh: float | None
    hypothetical_kwh: float | None
    delta_kwh: float | None
    delta_cost: float | None
    currency: str | None


class WhatIfResult(BaseModel):
    asset_code: str
    asset_name: str
    horizon_h: float
    baseline_conditions: WhatIfConditions
    hypothetical_conditions: WhatIfConditions
    baseline: WhatIfDistribution
    hypothetical: WhatIfDistribution
    delta_p50_h: float | None
    energy: WhatIfEnergy
    components_modelled: int
    exact_processes: int
    narrative: str
    computed_ms: int
