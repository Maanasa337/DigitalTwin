"""MLflow file-store registry wrapper for model versioning, promotion, and archival."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_STORE = "file:///data/mlruns"


class ModelStore:
    """Thin wrapper around MLflow's tracking and model registry APIs.

    Uses a local file store by default (no MLflow server needed).
    """

    def __init__(self, tracking_uri: str = DEFAULT_STORE) -> None:
        self.tracking_uri = tracking_uri
        self._mlflow: Any = None

    def _get_mlflow(self) -> Any:
        if self._mlflow is None:
            import mlflow
            mlflow.set_tracking_uri(self.tracking_uri)
            self._mlflow = mlflow
        return self._mlflow

    def log_model(
        self,
        model: Any,
        name: str,
        artifact_path: str = "model",
        metrics: dict[str, float] | None = None,
        params: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Log a model to an MLflow run and return the run ID."""
        mlflow = self._get_mlflow()
        with mlflow.start_run(run_name=name) as run:
            if params:
                mlflow.log_params(params)
            if metrics:
                mlflow.log_metrics(metrics)
            if tags:
                mlflow.set_tags(tags)
            mlflow.sklearn.log_model(model, artifact_path)
            return run.info.run_id

    def load_model(self, run_id: str, artifact_path: str = "model") -> Any:
        """Load a model from an MLflow run."""
        mlflow = self._get_mlflow()
        return mlflow.sklearn.load_model(f"runs:/{run_id}/{artifact_path}")

    def list_runs(self, experiment_name: str = "Default") -> list[dict[str, Any]]:
        """List all runs in an experiment."""
        mlflow = self._get_mlflow()
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            return []
        runs = mlflow.search_runs(experiment_ids=[experiment.experiment_id])
        return runs.to_dict(orient="records") if hasattr(runs, "to_dict") else []
