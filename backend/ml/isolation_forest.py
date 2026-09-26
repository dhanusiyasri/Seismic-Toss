"""Portable Isolation Forest anomaly detector for normal-condition learning.

The model is persisted with joblib, so it must be loaded with the same
scikit-learn major/minor version that created it.  MineWatch therefore stores
the training sklearn version in metadata and automatically retrains the
prototype artifact from the local SQLite data when a version mismatch is
found.  This avoids unsafe cross-version unpickling warnings during normal
runs while keeping the project easy to run on a developer machine.
"""
from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import threading

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest

from .feature_engineering import build_features, model_matrix

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "isolation_forest.joblib"
META_PATH = ARTIFACT_DIR / "isolation_forest_metadata.json"
DB_PATH = Path(__file__).resolve().parents[1] / "sensor_data.db"

_RETRAIN_LOCK = threading.Lock()


def _current_version() -> str:
    return str(sklearn.__version__)


def _metadata_is_compatible() -> bool:
    """Return True only when the persisted model matches this sklearn version."""
    if not MODEL_PATH.exists() or not META_PATH.exists():
        return False
    try:
        metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
        return metadata.get("sklearn_version") == _current_version()
    except (OSError, ValueError, TypeError):
        return False


def train_isolation_forest(features: pd.DataFrame, contamination=0.03, seed=42):
    X = model_matrix(features)
    model = IsolationForest(
        n_estimators=300,
        contamination=contamination,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(X)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    META_PATH.write_text(
        json.dumps(
            {
                "features": list(X.columns),
                "contamination": contamination,
                "training_rows": len(X),
                "sklearn_version": _current_version(),
                "model_type": "IsolationForest",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return model


def _retrain_from_local_database() -> None:
    """Retrain once using normal-condition rows from the bundled SQLite DB."""
    with _RETRAIN_LOCK:
        if _metadata_is_compatible():
            return

        if not DB_PATH.exists():
            raise RuntimeError(
                f"Isolation Forest artifact is missing/incompatible and database was not found: {DB_PATH}"
            )

        with sqlite3.connect(DB_PATH) as conn:
            raw = pd.read_sql_query(
                "SELECT * FROM gateway_readings ORDER BY server_timestamp",
                conn,
            )

        if raw.empty:
            raise RuntimeError(
                "Isolation Forest artifact is missing/incompatible and the gateway_readings table is empty. "
                "Run the training script after collecting normal sensor data."
            )

        features = build_features(raw)
        normal_mask = raw["edge_risk"].astype(str).str.upper().eq("NORMAL")
        normal_features = features.loc[normal_mask.values].copy()

        # The prototype needs enough observations to learn a stable baseline.
        # If the bundled/demo DB has too few NORMAL labels, use the earliest
        # lower-risk observations as the documented fallback.
        if len(normal_features) < 100:
            normal_features = features.iloc[: max(100, int(len(features) * 0.5))].copy()

        train_isolation_forest(normal_features)


def score_isolation_forest(features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    if out.empty:
        out["if_raw"] = pd.Series(dtype=float)
        out["if_anomaly_score"] = pd.Series(dtype=float)
        out["if_label"] = pd.Series(dtype=str)
        return out

    # Never unpickle a model produced by a different sklearn version.
    if not _metadata_is_compatible():
        _retrain_from_local_database()

    model = joblib.load(MODEL_PATH)
    X = model_matrix(features)

    # decision_function: positive = inlier. Convert relative ordering to 0..100.
    raw = model.decision_function(X)
    lo, hi = np.percentile(raw, [2, 98]) if len(raw) > 2 else (raw.min(), raw.max())
    score = np.clip((hi - raw) / max(hi - lo, 1e-9) * 100.0, 0, 100)
    out["if_raw"] = raw
    out["if_anomaly_score"] = score
    out["if_label"] = np.where(model.predict(X) == -1, "ANOMALY", "NORMAL")
    return out
