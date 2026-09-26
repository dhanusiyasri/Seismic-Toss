"""Temporal evidence for MineWatch: change points, persistence and trend."""
from __future__ import annotations
import numpy as np
import pandas as pd


def _series(df, col, default=0.0):
    if col not in df:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default)


def page_hinkley(values, delta=0.01, threshold=4.0):
    """Return a simple two-sided Page-Hinkley change indicator per sample."""
    x = np.asarray(values, dtype=float)
    if len(x) == 0:
        return np.array([], dtype=float)
    mean = 0.0; pos = 0.0; neg = 0.0; out = np.zeros(len(x), dtype=float)
    for i, v in enumerate(x):
        mean += (v - mean) / (i + 1)
        pos = max(0.0, pos + v - mean - delta)
        neg = min(0.0, neg + v - mean + delta)
        if pos > threshold or abs(neg) > threshold:
            out[i] = 1.0
            pos = 0.0; neg = 0.0
    return out


def add_temporal_evidence(features: pd.DataFrame, anomaly_score_col="anomaly_score", window=6):
    out = features.copy()
    anomaly = _series(out, anomaly_score_col)
    out["change_point_score"] = page_hinkley(anomaly / 100.0) * 100.0
    out["anomaly_rolling_mean"] = anomaly.rolling(window, min_periods=1).mean()
    out["anomaly_rolling_max"] = anomaly.rolling(window, min_periods=1).max()
    out["persistence_score"] = (
        anomaly.ge(45.0).rolling(window, min_periods=1).mean() * 100.0
    )
    # Risk trend is based on the slope of recent anomaly evidence.
    def slope(values):
        y = np.asarray(values, dtype=float)
        if len(y) < 2 or np.allclose(y, y[0]): return 0.0
        x = np.arange(len(y), dtype=float)
        return float(np.polyfit(x, y, 1)[0])
    out["anomaly_trend"] = anomaly.rolling(window, min_periods=2).apply(slope, raw=True).fillna(0.0)
    out["trend_score"] = np.clip(out["anomaly_trend"] * 100.0 / 15.0, 0, 100)
    return out
