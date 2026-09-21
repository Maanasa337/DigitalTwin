"""Imports every ORM model so Base.metadata is complete (Alembic, tests)."""

from app.core.models import AuditLog, User
from app.modules.analytics.models import EnergyBaseline, KpiDefinition, KpiValue, Shift, Tariff
from app.modules.assets.models import AasSubmodel, Asset, Component, FailureMode, Line, Plant, Sensor
from app.modules.maintenance.models import (
    Schedule,
    ScheduleItem,
    Technician,
    TechnicianAvailability,
    WorkOrder,
    WorkOrderTask,
)
from app.modules.pdm.models import BenchmarkRun, Model, ModelMetric, Prediction
from app.modules.reports.models import Report, ReportSchedule
from app.modules.simulation.models import Scenario, ScenarioRun
from app.modules.telemetry.models import (
    Alarm,
    AlarmAction,
    AlarmRule,
    AssetStateEvent,
    EnergyReading,
    ProductionCount,
    Telemetry,
    Waveform,
)
from app.modules.voice.models import IntentExample, VoiceAction, VoiceSession, VoiceTurn
from app.modules.xai.models import (
    Counterfactual,
    Explanation,
    ExplanationFeedback,
    ExplanationQualityMetric,
    KnowledgeBaseEntry,
    Narration,
    NarrationAudit,
)

__all__ = [
    "AasSubmodel", "Alarm", "AlarmAction", "AlarmRule", "Asset", "AssetStateEvent", "AuditLog",
    "BenchmarkRun", "Component", "Counterfactual", "EnergyBaseline", "EnergyReading", "Explanation",
    "ExplanationFeedback", "ExplanationQualityMetric", "FailureMode", "IntentExample",
    "KnowledgeBaseEntry", "KpiDefinition", "KpiValue", "Line", "Model", "ModelMetric", "Narration",
    "NarrationAudit", "Plant", "Prediction", "ProductionCount", "Report", "ReportSchedule",
    "Scenario", "ScenarioRun", "Schedule", "ScheduleItem", "Sensor", "Shift", "Tariff", "Technician",
    "TechnicianAvailability", "Telemetry", "User", "VoiceAction", "VoiceSession", "VoiceTurn",
    "Waveform", "WorkOrder", "WorkOrderTask",
]  # fmt: skip
