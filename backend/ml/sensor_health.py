"""Sensor/data-quality confidence for MineWatch."""
from __future__ import annotations
import numpy as np
import pandas as pd


def _series(df: pd.DataFrame, column: str, default: float) -> pd.Series:
    value = df[column] if column in df.columns else pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(value, errors="coerce").fillna(default)


def add_sensor_health(features: pd.DataFrame):
    out = features.copy()
    available = _series(out, "node_data_available", 1.0)
    esp = _series(out, "esp_now_available", 1.0)
    sd = _series(out, "sd_available", 1.0)
    required = ["n1_tilt", "n1_accel_deviation", "n1_fsr", "n1_vibration_events"]
    if all(c in out.columns for c in required):
        missing = out[required].isna().mean(axis=1)
    else:
        missing = pd.Series(0.0, index=out.index)
    health = 100.0 - missing * 60.0 - (1.0 - available) * 10.0 - (1.0 - esp) * 15.0 - (1.0 - sd) * 5.0
    out["sensor_health_score"] = np.clip(health, 0, 100)
    out["sensor_health_status"] = np.select(
        [out["sensor_health_score"] < 50, out["sensor_health_score"] < 80],
        ["FAULT", "DEGRADED"], default="HEALTHY"
    )
    return out
