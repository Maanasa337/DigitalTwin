"""Control HTTP API (internal network only; the platform API proxies it with auth)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from sim.engine import InvalidRequestError, UnknownAssetError
from sim.export import MAX_HOURS, export_run
from sim.live import MAX_TIME_SCALE, MIN_TIME_SCALE, LiveRuntime, UnknownScenarioError


class ScenarioRequest(BaseModel):
    scenario_code: str


class FaultRequest(BaseModel):
    asset: str
    failure_mode: str
    mode: Literal["sudden", "gradual"] = "gradual"
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    metric: str | None = None
    duration_s: float | None = Field(default=None, gt=0.0)


class TimeScaleRequest(BaseModel):
    factor: float = Field(ge=MIN_TIME_SCALE, le=MAX_TIME_SCALE)


class ResetRequest(BaseModel):
    component_code: str | None = None


class ExportRequest(BaseModel):
    scenario_code: str | None = None
    hours: float = Field(gt=0.0, le=MAX_HOURS)
    sample_period_s: float = Field(default=10.0, gt=0.0)
    seed: int | None = None


def create_app(runtime: LiveRuntime, export_dir: Path) -> FastAPI:
    app = FastAPI(title="TwinVoice Simulator", version="0.1.0")
    catalog_document = runtime.catalog.document()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/catalog")
    def catalog() -> dict[str, Any]:
        return catalog_document

    @app.get("/status")
    def status() -> dict[str, Any]:
        return runtime.status()

    @app.post("/scenario")
    def start_scenario(body: ScenarioRequest) -> dict[str, Any]:
        try:
            return runtime.start_scenario(body.scenario_code)
        except UnknownScenarioError:
            raise HTTPException(404, f"unknown scenario {body.scenario_code}") from None

    @app.post("/faults")
    def inject_fault(body: FaultRequest) -> dict[str, Any]:
        try:
            with runtime.lock:
                runtime.engine.inject_fault(
                    body.asset,
                    body.failure_mode,
                    body.mode,
                    body.severity,
                    body.metric,
                    body.duration_s,
                )
        except UnknownAssetError:
            raise HTTPException(404, f"unknown asset {body.asset}") from None
        except InvalidRequestError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"accepted": True, "asset": body.asset, "failure_mode": body.failure_mode}

    @app.post("/time-scale")
    def time_scale(body: TimeScaleRequest) -> dict[str, float]:
        return {"time_scale": runtime.set_time_scale(body.factor)}

    @app.post("/reset/{asset}")
    def reset(asset: str, body: ResetRequest | None = None) -> dict[str, Any]:
        component = body.component_code if body else None
        try:
            with runtime.lock:
                codes = runtime.engine.reset(asset, component)
        except UnknownAssetError:
            raise HTTPException(404, f"unknown asset {asset}") from None
        except InvalidRequestError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"asset": asset, "reset_components": codes}

    @app.post("/export")
    async def export(body: ExportRequest) -> dict[str, Any]:
        if body.scenario_code is not None and body.scenario_code not in runtime.catalog.scenarios:
            raise HTTPException(404, f"unknown scenario {body.scenario_code}")
        result = await run_in_threadpool(
            export_run,
            runtime.catalog,
            hours=body.hours,
            out_dir=export_dir,
            period_s=body.sample_period_s,
            scenario_code=body.scenario_code,
            seed=body.seed,
        )
        return {"path": str(result.path), "rows": result.rows, "columns": result.columns}

    return app
