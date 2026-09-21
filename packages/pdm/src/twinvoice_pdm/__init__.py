"""TwinVoice PDM — Predictive Maintenance pipeline library.

Modules:
    features  — sliding-window feature extraction
    anomaly   — IsolationForest anomaly / health-index
    failure   — LightGBM multiclass failure classification
    rul       — LightGBM regression + MAPIE conformal intervals
    registry  — MLflow model registry wrapper
    datasets  — synthetic data loading from simulator exports
"""

__version__ = "0.1.0"
