"""Portable, temperature-calibrated ML layer for MineWatch.

The model is intentionally small enough to run locally/offline.  It produces
class probabilities from a multiclass logistic classifier and calibrates those
probabilities with a scalar temperature fitted on a held-out calibration set.

Important: training labels in this prototype come from simulator/edge-risk
states plus physics-informed synthetic states.  They are not mine-ground-truth
labels and therefore do not constitute safety certification.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, log_loss
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

MODEL_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = MODEL_DIR / "calibrated_risk_model.json"
METADATA_PATH = MODEL_DIR / "calibrated_risk_model_metadata.json"

FEATURES = [
    "n1_tilt", "n1_tilt_rate", "n1_accel_deviation", "n1_fsr",
    "n1_fsr_change", "n1_vibration_events",
    "n1_tilt_rolling_mean", "n1_tilt_rolling_std",
    "n1_accel_deviation_rolling_mean", "n1_accel_deviation_rolling_std",
    "n1_fsr_rolling_std", "n1_vibration_events_rolling_mean",
    "n1_vibration_events_rolling_std",
    "n2_tilt", "n2_accel_deviation", "n2_fsr",
    "node_tilt_difference", "node_accel_difference", "node_fsr_difference",
    "node_data_available",
]

def _matrix(features: pd.DataFrame) -> pd.DataFrame:
    x = features.reindex(columns=FEATURES, fill_value=np.nan).copy()
    x = x.replace([np.inf, -np.inf], np.nan)
    x = x.apply(pd.to_numeric, errors="coerce")
    return x

def _ramp(v, low, high):
    return float(np.clip((abs(v) - low) / max(high - low, 1e-9) * 100, 0, 100))

def physics_score(row: pd.Series) -> float:
    """Independent engineering-informed screening score (0-100).

    These bands are prototype screening bands, not statutory or site-specific
    geotechnical thresholds.
    """
    def f(k, d=0.0):
        try:
            v = float(row.get(k, d))
            return v if np.isfinite(v) else d
        except (TypeError, ValueError):
            return d

    tilt = _ramp(f("n1_tilt"), 1.0, 8.0)
    tilt_rate = _ramp(f("n1_tilt_rate"), 0.05, 0.50)
    accel = _ramp(f("n1_accel_deviation"), 0.03, 0.20)
    vibration = float(np.clip(f("n1_vibration_events") / 4.0 * 100, 0, 100))
    fsr = _ramp(f("n1_fsr"), 70.0, 450.0)
    fsr_rate = _ramp(f("n1_fsr_change"), 15.0, 120.0)
    cross_tilt = _ramp(f("node_tilt_difference"), 0.5, 5.0)
    cross_fsr = _ramp(f("node_fsr_difference"), 40.0, 250.0)
    return float(np.clip(
        0.28 * tilt + 0.12 * tilt_rate + 0.18 * accel +
        0.12 * vibration + 0.10 * fsr + 0.06 * fsr_rate +
        0.08 * cross_tilt + 0.06 * cross_fsr, 0, 100
    ))

def load_model() -> dict:
    with MODEL_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def _softmax(z):
    z = z - np.max(z, axis=1, keepdims=True)
    e = np.exp(np.clip(z, -50, 50))
    return e / np.sum(e, axis=1, keepdims=True)

def _apply_temperature(logits, temperature):
    return _softmax(logits / max(float(temperature), 1e-6))

def score_calibrated(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        out = features.copy()
        for col in ["ml_probability_score", "ml_risk_score", "ml_risk", "physics_score", "ml_confidence",
                    "prob_normal", "prob_warning", "prob_critical"]:
            out[col] = []
        return out

    artifact = load_model()
    X = _matrix(features)
    medians = pd.Series(artifact["imputer_medians"], index=FEATURES, dtype=float)
    X = X.fillna(medians).fillna(0.0)

    mean = np.asarray(artifact["scaler_mean"], dtype=float)
    scale = np.asarray(artifact["scaler_scale"], dtype=float)
    coef = np.asarray(artifact["coef"], dtype=float)
    intercept = np.asarray(artifact["intercept"], dtype=float)
    classes = [str(c) for c in artifact["classes"]]
    temperature = float(artifact.get("temperature", 1.0))

    xs = (X.to_numpy(dtype=float) - mean) / np.where(scale == 0, 1.0, scale)
    logits = xs @ coef.T + intercept
    proba = _apply_temperature(logits, temperature)
    probabilities = {c: proba[:, i] for i, c in enumerate(classes)}

    normal = probabilities.get("NORMAL", np.zeros(len(X)))
    warning = probabilities.get("WARNING", np.zeros(len(X)))
    critical = probabilities.get("CRITICAL", np.zeros(len(X)))

    # Anomaly score means "departure from the normal class", not final risk.
    ml_probability_score = np.clip((1.0 - normal) * 100.0, 0, 100)
    physics = features.apply(physics_score, axis=1).to_numpy(dtype=float)
    confidence = np.max(proba, axis=1) * 100.0
    sorted_proba = np.sort(proba, axis=1)
    decision_margin = (sorted_proba[:, -1] - sorted_proba[:, -2]) * 100.0
    ml_risk_score = np.clip(
        warning * 55.0 + critical * 100.0 + (1.0 - normal) * 10.0, 0, 100
    )
    ml_risk = np.select(
        [ml_risk_score >= 75, ml_risk_score >= 45],
        ["CRITICAL", "WARNING"], default="NORMAL"
    )

    out = features.copy()
    out["ml_probability_score"] = ml_probability_score
    out["ml_risk_score"] = ml_risk_score
    out["ml_risk"] = ml_risk
    out["physics_score"] = physics
    out["ml_confidence"] = confidence
    out["decision_margin"] = decision_margin
    out["prob_normal"] = normal * 100.0
    out["prob_warning"] = warning * 100.0
    out["prob_critical"] = critical * 100.0
    return out

def _fit_temperature(logits, y_true, classes):
    """Fit a single temperature using a small deterministic grid.

    A scalar temperature preserves class ordering while correcting
    over/under-confidence.  No extra runtime dependency is required.
    """
    best_t, best_loss = 1.0, float("inf")
    for t in np.linspace(0.50, 3.00, 101):
        p = _apply_temperature(logits, t)
        loss = log_loss(y_true, p, labels=classes)
        if loss < best_loss:
            best_loss, best_t = loss, float(t)
    return best_t, best_loss

def train_model(X: pd.DataFrame, y: pd.Series, metadata: dict) -> dict:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    raw = _matrix(X)
    medians = raw.median(numeric_only=True).reindex(FEATURES).fillna(0.0)
    raw = raw.fillna(medians).fillna(0.0)

    # Chronological information is not available in the synthetic matrix, so
    # use stratified splits with fixed seeds and keep a distinct calibration set.
    x_train, x_hold, y_train, y_hold = train_test_split(
        raw, y, test_size=0.40, random_state=42, stratify=y
    )
    x_cal, x_test, y_cal, y_test = train_test_split(
        x_hold, y_hold, test_size=0.50, random_state=43, stratify=y_hold
    )

    scaler = StandardScaler()
    x_train_s = scaler.fit_transform(x_train)
    x_cal_s = scaler.transform(x_cal)
    x_test_s = scaler.transform(x_test)

    model = LogisticRegression(max_iter=3000, C=1.5, class_weight=None)
    model.fit(x_train_s, y_train)

    cal_logits = x_cal_s @ model.coef_.T + model.intercept_
    temperature, cal_logloss = _fit_temperature(cal_logits, y_cal, model.classes_)
    test_logits = x_test_s @ model.coef_.T + model.intercept_
    test_proba = _apply_temperature(test_logits, temperature)
    pred = np.asarray(model.classes_)[np.argmax(test_proba, axis=1)]

    metrics = {
        "accuracy": float(accuracy_score(y_test, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_test, pred)),
        "log_loss": float(log_loss(y_test, test_proba, labels=model.classes_)),
        "calibration_log_loss": float(cal_logloss),
        "classification_report": classification_report(
            y_test, pred, output_dict=True, zero_division=0
        ),
    }

    artifact = {
        "model": "multiclass_logistic_regression_temperature_scaled",
        "classes": [str(c) for c in model.classes_],
        "features": FEATURES,
        "imputer_medians": [float(medians[c]) for c in FEATURES],
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": model.coef_.tolist(),
        "intercept": model.intercept_.tolist(),
        "temperature": temperature,
    }
    MODEL_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    METADATA_PATH.write_text(json.dumps({
        **metadata,
        "features": FEATURES,
        "model": "multiclass logistic regression + temperature scaling",
        "metrics": metrics,
        "calibration": {"method": "scalar temperature scaling", "temperature": temperature},
        "runtime": "portable JSON coefficients; no sklearn pickle required",
        "warning": "Metrics and calibration are against simulator/edge-risk labels, not field ground truth.",
    }, indent=2), encoding="utf-8")
    return metrics
