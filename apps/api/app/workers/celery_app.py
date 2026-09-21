"""Celery application: broker on Valkey, JSON serializer, beat schedule for periodic inference."""

from celery import Celery
from celery.schedules import crontab

import app.models  # noqa: F401  — registers every table so cross-module FKs resolve in the worker
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "twinvoice",
    broker=settings.valkey_url.replace("redis://", "redis://", 1),
    backend=settings.valkey_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Auto-discover tasks in the workers/tasks directory
    imports=[
        "app.workers.tasks.infer",
        "app.workers.tasks.train",
        "app.workers.tasks.explain",
        "app.workers.tasks.maintenance",
        "app.workers.tasks.rollup",
        "app.workers.tasks.report",
    ],
)

celery_app.conf.beat_schedule = {
    "infer-all-assets": {
        "task": "app.workers.tasks.infer.infer_all_assets",
        "schedule": 30.0,  # seconds
    },
    # M7: auto work orders follow inference, so they run a little less often than it.
    "raise-predictive-orders": {
        "task": "app.workers.tasks.maintenance.raise_predictive_orders",
        "schedule": 300.0,
    },
    "score-closed-orders": {
        "task": "app.workers.tasks.maintenance.score_closed_orders",
        "schedule": crontab(hour="1", minute="0"),
    },
    # M8: hourly incremental rollup of the day in progress, plus shift and nightly baselines.
    "rollup-day": {
        "task": "app.workers.tasks.rollup.rollup_kpis",
        "schedule": crontab(minute="5"),
        "kwargs": {"period": "day"},
    },
    "rollup-shift": {
        "task": "app.workers.tasks.rollup.rollup_kpis",
        "schedule": crontab(minute="0", hour="6,14,22"),
        "kwargs": {"period": "shift"},
    },
    # M10: schedules are rows, so beat only has to ask once a minute which of them are due.
    "run-report-schedules": {
        "task": "app.workers.tasks.report.run_report_schedules",
        "schedule": 60.0,
    },
    "refresh-energy-baselines": {
        "task": "app.workers.tasks.rollup.refresh_energy_baselines",
        "schedule": crontab(hour="2", minute="30"),
    },
}
