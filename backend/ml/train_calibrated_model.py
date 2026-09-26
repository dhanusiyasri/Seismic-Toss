"""Train the self-contained prototype MineWatch classifier."""
from __future__ import annotations
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from .feature_engineering import build_features
from .calibrated_model import train_model, FEATURES

BASE = Path(__file__).resolve().parents[1]
DB = BASE / "sensor_data.db"

def load_real_demo_rows():
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query("SELECT * FROM gateway_readings ORDER BY server_timestamp", conn)

def make_synthetic(n=16000, seed=42):
    rng = np.random.default_rng(seed)
    labels = rng.choice(["NORMAL", "WARNING", "CRITICAL"], size=n, p=[0.50, 0.30, 0.20])
    rows = []
    for label in labels:
        if label == "NORMAL":
            tilt = rng.uniform(0.05, 2.0); accel = rng.uniform(0.0, 0.08); fsr = rng.uniform(0, 70)
            vib = rng.binomial(1, .05); tilt_rate = rng.normal(0, .04); fsr_change = rng.normal(0, 8); n2_factor = rng.uniform(.85, 1.05)
            tilt_std, accel_std, fsr_std, vib_std = .15, .008, 6, .15
        elif label == "WARNING":
            tilt = rng.uniform(2.0, 7.0); accel = rng.uniform(.06, .20); fsr = rng.uniform(60, 420)
            vib = rng.binomial(4, .35); tilt_rate = rng.uniform(.03, .45); fsr_change = rng.normal(35, 30); n2_factor = rng.uniform(.55, .95)
            tilt_std, accel_std, fsr_std, vib_std = .45, .02, 25, .6
        else:
            tilt = rng.uniform(7.0, 15.0); accel = rng.uniform(.16, .40); fsr = rng.uniform(300, 850)
            vib = rng.integers(2, 5); tilt_rate = rng.uniform(.25, 1.5); fsr_change = rng.normal(100, 45); n2_factor = rng.uniform(.35, .75)
            tilt_std, accel_std, fsr_std, vib_std = .9, .05, 55, .9

        n2_tilt = max(0, tilt * n2_factor + rng.normal(0, .15))
        n2_accel = max(0, accel * rng.uniform(.7, 1.0) + rng.normal(0, .01))
        n2_fsr = max(0, fsr * rng.uniform(.65, 1.0) + rng.normal(0, 8))
        rows.append({
            "n1_tilt": abs(tilt), "n1_tilt_rate": tilt_rate, "n1_accel_deviation": abs(accel),
            "n1_fsr": fsr, "n1_fsr_change": fsr_change, "n1_vibration_events": vib,
            "n1_tilt_rolling_mean": max(0, tilt + rng.normal(0, tilt_std)),
            "n1_tilt_rolling_std": abs(rng.normal(tilt_std, tilt_std * .25)),
            "n1_accel_deviation_rolling_mean": max(0, accel + rng.normal(0, accel_std)),
            "n1_accel_deviation_rolling_std": abs(rng.normal(accel_std, accel_std * .25)),
            "n1_fsr_rolling_std": abs(rng.normal(fsr_std, fsr_std * .20)),
            "n1_vibration_events_rolling_mean": max(0, vib + rng.normal(0, vib_std)),
            "n1_vibration_events_rolling_std": abs(rng.normal(vib_std, vib_std * .25)),
            "n2_tilt": n2_tilt, "n2_accel_deviation": n2_accel, "n2_fsr": n2_fsr,
            "node_tilt_difference": abs(tilt - n2_tilt),
            "node_accel_difference": abs(accel - n2_accel),
            "node_fsr_difference": abs(fsr - n2_fsr),
            "node_data_available": 1.0,
            "target": label,
        })
    return pd.DataFrame(rows)

def main():
    parts = []
    if DB.exists():
        raw = load_real_demo_rows()
        if not raw.empty:
            f = build_features(raw)
            y = f["edge_risk"].astype(str).str.upper().map({
                "NORMAL": "NORMAL", "SIGNIFICANT_MOVEMENT": "WARNING", "CRITICAL_MOVEMENT": "CRITICAL"
            })
            demo = f.copy()
            demo["target"] = y
            parts.append(demo[[*FEATURES, "target"]].dropna(subset=["target"]))
    parts.append(make_synthetic())
    data = pd.concat(parts, ignore_index=True)
    metrics = train_model(data[FEATURES], data["target"], {
        "training_rows": int(len(data)),
        "sources": ["existing gateway simulator database", "physics-informed synthetic sensor states"],
        "purpose": "prototype scenario-consistent risk classification with held-out temperature calibration",
    })
    print("Training rows:", len(data))
    print("Class distribution:\n", data.target.value_counts())
    print("Accuracy:", round(metrics["accuracy"], 4))
    print("Balanced accuracy:", round(metrics["balanced_accuracy"], 4))
    print("Test log loss:", round(metrics["log_loss"], 4))
    print("Calibration log loss:", round(metrics["calibration_log_loss"], 4))

if __name__ == "__main__":
    main()
