"""Multi-node spatial evidence for MineWatch.

The score asks whether neighboring nodes show abnormal behaviour together,
rather than treating a large difference between nodes as spatial correlation.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _ramp(s, low, high):
    return np.clip((s.abs() - low) / max(high - low, 1e-9) * 100.0, 0, 100)


def add_spatial_evidence(features: pd.DataFrame):
    out = features.copy()
    n1_tilt = pd.to_numeric(out.get("n1_tilt", 0), errors="coerce").fillna(0)
    n2_tilt = pd.to_numeric(out.get("n2_tilt", 0), errors="coerce").fillna(0)
    n1_acc = pd.to_numeric(out.get("n1_accel_deviation", 0), errors="coerce").fillna(0)
    n2_acc = pd.to_numeric(out.get("n2_accel_deviation", 0), errors="coerce").fillna(0)
    n1_fsr = pd.to_numeric(out.get("n1_fsr", 0), errors="coerce").fillna(0)
    n2_fsr = pd.to_numeric(out.get("n2_fsr", 0), errors="coerce").fillna(0)
    n1_vib = pd.to_numeric(out.get("n1_vibration_events", 0), errors="coerce").fillna(0)
    n2_vib = pd.to_numeric(out.get("n2_vibration_events", 0), errors="coerce").fillna(0)
    available = pd.to_numeric(out.get("node_data_available", 0), errors="coerce").fillna(0)

    n1_score = (0.35*_ramp(n1_tilt,1,8) + 0.25*_ramp(n1_acc,.03,.20) + 0.25*_ramp(n1_fsr,70,450) + 0.15*np.clip(n1_vib/4*100,0,100))
    n2_score = (0.35*_ramp(n2_tilt,1,8) + 0.25*_ramp(n2_acc,.03,.20) + 0.25*_ramp(n2_fsr,70,450) + 0.15*np.clip(n2_vib/4*100,0,100))
    both_abnormal = (n1_score >= 45) & (n2_score >= 45) & (available >= 1)
    similar_direction = 100.0 - np.clip(np.abs(n1_score - n2_score), 0, 100)
    simultaneous_strength = (np.minimum(n1_score, n2_score) * 0.7 + similar_direction * 0.3)
    out["node1_risk_signal"] = np.clip(n1_score, 0, 100)
    out["node2_risk_signal"] = np.clip(n2_score, 0, 100)
    out["multi_node_active"] = both_abnormal.astype(float)
    out["spatial_correlation_score"] = np.where(both_abnormal, simultaneous_strength, 0.0)
    return out
