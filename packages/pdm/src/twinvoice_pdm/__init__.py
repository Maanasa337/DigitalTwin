"""TwinVoice PDM — Predictive Maintenance pipeline library.

Modules:
    features  — sliding-window feature extraction
    anomaly   — IsolationForest anomaly / health-index
    failure   — LightGBM multiclass failure classification
    rul       — LightGBM regression + MAPIE conformal intervals
    registry  — MLflow wrapper, on-disk model bundles, ONNX export and parity
    datasets  — simulator exports and the C-MAPSS / AI4I 2020 / MetroPT-3 loaders
    benchmark — the FR-PM-09 benchmark runner shared by the CLI and the worker
"""

__version__ = "0.1.0"
