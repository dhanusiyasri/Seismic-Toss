"""Hybrid anomaly layer: Isolation Forest + optional calibrated classifier."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .calibrated_model import score_calibrated
from .isolation_forest import score_isolation_forest


def score_dataframe(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return features.copy()
    result = score_isolation_forest(features)
    calibrated = score_calibrated(features)
    for col in ["ml_risk_score", "ml_risk", "physics_score", "ml_confidence", "decision_margin", "prob_normal", "prob_warning", "prob_critical"]:
        if col in calibrated:
            result[col] = calibrated[col].to_numpy()
    # Isolation Forest is the authoritative unsupervised anomaly evidence.
    result["anomaly_raw"] = result["if_raw"].astype(float)
    result["anomaly_score"] = result["if_anomaly_score"].astype(float)
    result["anomaly_label"] = result["if_label"]
    # Keep calibrated classifier as secondary contextual evidence.
    result["classifier_anomaly_score"] = result.get("ml_probability_score", 0.0)
    return result
