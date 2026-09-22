"""PdM API (M5): benchmark runs, job status and ONNX download, against compose `postgres`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.models import AuditLog
from app.modules.pdm import service as pdm_service
from app.modules.pdm.models import BenchmarkRun
from app.modules.pdm.service import ModelService
from tests.conftest import auth

V1 = "/api/v1"


@pytest.fixture
def raw_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A data/raw with AI4I present and C-MAPSS missing."""
    raw = tmp_path / "raw"
    (raw / "ai4i").mkdir(parents=True)
    (raw / "ai4i" / "ai4i2020.csv").write_text("x")
    monkeypatch.setattr(pdm_service, "get_settings", lambda: Settings(raw_data_dir=str(raw)))
    return raw


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, bool]]:
    """Capture benchmark enqueues instead of sending them to the dev broker."""
    from app.workers.tasks import benchmark

    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        benchmark.run_benchmark_task, "delay", lambda run_id, quick=False: calls.append((run_id, quick))
    )
    return calls


def test_running_a_benchmark_queues_it_and_audits_it(
    client: TestClient, session: Session, raw_dir: Path, queued: list[tuple[str, bool]]
) -> None:
    response = client.post(f"{V1}/benchmarks/run", json={"datasets": ["AI4I"], "quick": True}, headers=auth("engineer"))
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "running"
    assert body["datasets"] == ["AI4I"]
    assert body["seed"] == 42
    assert body["error"] is None
    assert body["targets"]["AI4I"]["auc"] == {"op": "ge", "value": 0.96}
    assert body["targets"]["FD001"]["rmse"] == {"op": "le", "value": 13.0}
    assert queued == [(body["id"], True)]

    audit = session.scalars(select(AuditLog).where(AuditLog.entity == "benchmark_runs")).all()
    assert [a.action for a in audit] == ["run"]


def test_missing_raw_data_is_a_409_that_says_how_to_fetch_it(
    client: TestClient, raw_dir: Path, queued: list[tuple[str, bool]]
) -> None:
    response = client.post(f"{V1}/benchmarks/run", json={"datasets": ["FD001", "AI4I"]}, headers=auth("admin"))
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "python data/download.py cmapss" in response.json()["detail"]
    assert queued == []


def test_only_engineers_and_admins_run_benchmarks(client: TestClient, raw_dir: Path) -> None:
    response = client.post(f"{V1}/benchmarks/run", json={"datasets": ["AI4I"]}, headers=auth("technician"))
    assert response.status_code == 403


def test_unknown_datasets_are_rejected(client: TestClient, raw_dir: Path) -> None:
    response = client.post(f"{V1}/benchmarks/run", json={"datasets": ["FD009"]}, headers=auth("engineer"))
    assert response.status_code == 422
    assert client.post(f"{V1}/benchmarks/run", json={"datasets": []}, headers=auth("engineer")).status_code == 422


def finished_run(session: Session, report: Path | None, **overrides: Any) -> BenchmarkRun:
    run = BenchmarkRun(
        seed=7,
        datasets=["FD001"],
        results={"FD001": {"rmse": 12.2, "nasa_score": 231.9}},
        status="done",
        finished_at=datetime.now(UTC),
        git_sha="abc123",
        report_uri=f"file://{report.resolve().as_posix()}" if report else None,
        **overrides,
    )
    session.add(run)
    session.flush()
    return run


def test_listing_and_reading_runs(client: TestClient, session: Session, tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    report.write_text("# TwinVoice model benchmark\n| FD001 | rmse | 12.2 |", encoding="utf-8")
    run = finished_run(session, report)
    broken = BenchmarkRun(seed=1, datasets=["AI4I"], status="failed", results={"_error": {"message": "boom"}})
    session.add(broken)
    session.flush()

    page = client.get(f"{V1}/benchmarks?page=1&size=20", headers=auth("technician"))
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 2 and body["page"] == 1 and body["size"] == 20
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[str(run.id)]["results"] == {"FD001": {"rmse": 12.2, "nasa_score": 231.9}}
    assert by_id[str(broken.id)]["error"] == "boom"
    assert by_id[str(broken.id)]["results"] is None

    one = client.get(f"{V1}/benchmarks/{run.id}", headers=auth("manager")).json()
    assert one["git_sha"] == "abc123" and one["status"] == "done"

    md = client.get(f"{V1}/benchmarks/{run.id}/report.md", headers=auth("manager"))
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "| FD001 | rmse | 12.2 |" in md.text


def test_a_run_without_a_report_is_404(client: TestClient, session: Session) -> None:
    run = finished_run(session, None)
    assert client.get(f"{V1}/benchmarks/{run.id}/report.md", headers=auth("manager")).status_code == 404
    assert client.get(f"{V1}/benchmarks/{uuid.uuid4()}", headers=auth("manager")).status_code == 404


def test_the_benchmark_task_fills_in_results_and_the_report(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker path end to end, with the pdm runner stubbed to a fixed result."""
    import twinvoice_pdm.benchmark as bench

    from app.workers.tasks import benchmark

    run = BenchmarkRun(seed=42, datasets=["AI4I"], status="running")
    session.add(run)
    session.flush()

    class SameSession:
        def __call__(self) -> SameSession:
            return self

        def __enter__(self) -> Session:
            return session

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr("app.core.db.get_sessionmaker", lambda: SameSession())
    monkeypatch.setattr(
        "app.core.config.get_settings", lambda: Settings(raw_data_dir=str(tmp_path), benchmarks_dir=str(tmp_path))
    )
    monkeypatch.setattr(bench, "run_benchmark", lambda *a, **k: {"AI4I": {"auc": 0.97}})

    assert benchmark.run_benchmark_task.run(str(run.id), quick=True) == "done"
    session.refresh(run)
    assert run.status == "done"
    assert run.results == {"AI4I": {"auc": 0.97}}
    assert run.report_uri and Path(run.report_uri.removeprefix("file://")).read_text(encoding="utf-8").count("AI4I")

    monkeypatch.setattr(bench, "run_benchmark", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no data")))
    assert benchmark.run_benchmark_task.run(str(run.id)) == "failed"
    session.refresh(run)
    assert run.status == "failed" and run.results == {"_error": {"message": "no data"}}


# ── Jobs and ONNX ─────────────────────────────────────────────────────


def test_job_status_maps_celery_states(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    model_id = uuid.uuid4()

    class FakeResult:
        def __init__(self, job_id: str, app: object = None) -> None:
            self.state = {"done-job": "SUCCESS", "bad-job": "FAILURE"}.get(job_id, "STARTED")
            self.result = ValueError("unknown asset type 'x'") if job_id == "bad-job" else {"model_id": str(model_id)}

    monkeypatch.setattr("celery.result.AsyncResult", FakeResult)
    done = client.get(f"{V1}/jobs/done-job", headers=auth("engineer")).json()
    assert done == {"job_id": "done-job", "status": "done", "model_id": str(model_id), "error": None}
    assert client.get(f"{V1}/jobs/other", headers=auth("engineer")).json()["status"] == "running"
    failed = client.get(f"{V1}/jobs/bad-job", headers=auth("engineer")).json()
    assert failed["status"] == "failed" and failed["error"] == "unknown asset type 'x'"


def register(session: Session, onnx_uri: str | None) -> uuid.UUID:
    model = ModelService(session).register_model(
        None,
        name="rul-test",
        version=uuid.uuid4().hex[:8],
        task="rul",
        algorithm="lightgbm",
        dataset_ref="cmapss:FD001",
        dataset_hash="x",
        feature_set={"features": ["s_2_mean"]},
        artifact_uri="file:///nope/model.pkl",
        onnx_uri=onnx_uri,
        metrics=[{"split": "test", "metric": "onnx_parity_max_abs", "value": 3e-5}],
    )
    return model.id


def test_onnx_download(client: TestClient, session: Session, tmp_path: Path) -> None:
    onnx = tmp_path / "model.onnx"
    onnx.write_bytes(b"\x08\x07onnx-bytes")
    model_id = register(session, f"file://{onnx.resolve().as_posix()}")

    response = client.get(f"{V1}/models/{model_id}/onnx", headers=auth("technician"))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert "rul-test-" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.onnx"')
    assert response.content == b"\x08\x07onnx-bytes"

    metrics = client.get(f"{V1}/models/{model_id}/metrics", headers=auth("technician")).json()
    assert metrics[0]["metric"] == "onnx_parity_max_abs"


def test_onnx_download_is_404_without_an_export_or_file(client: TestClient, session: Session) -> None:
    for uri in (None, "file:///definitely/not/here.onnx"):
        response = client.get(f"{V1}/models/{register(session, uri)}/onnx", headers=auth("technician"))
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")
