"""Automated scenario validation for the MineWatch prototype AI pipeline.

This validates internal consistency on simulator-generated scenarios. It is not
field validation and should never be described as mine-safety certification.
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from ml.feature_engineering import build_features
from ml.anomaly_detector import score_dataframe
from ml.risk_engine import calculate_risk
from ml.temporal_analysis import add_temporal_evidence
from ml.spatial_analysis import add_spatial_evidence
from ml.sensor_health import add_sensor_health
from simulator.sensor_simulator import generate_gateway_packet, SCENARIOS


def packet_row(packet, timestamp):
    n1 = packet["node1"]
    n2 = packet["node2"]
    return {
        "server_timestamp": timestamp,
        "edge_risk": packet["risk"],
        "node1_accel_magnitude_g": n1["accel_magnitude_g"],
        "node1_accel_deviation_g": n1["accel_deviation_g"],
        "node1_gyro_magnitude_dps": n1["gyro_magnitude_dps"],
        "node1_roll_deg": n1["roll_deg"], "node1_pitch_deg": n1["pitch_deg"],
        "node1_fsr_raw": n1["fsr_raw"], "node1_vibration": n1["vibration"],
        "node1_vibration_events": n1["vibration_events"], "node1_tilt_change_deg": n1["tilt_change_deg"],
        "node2_online": 1, "node2_accel_magnitude_g": n2["accel_magnitude_g"],
        "node2_gyro_magnitude_dps": n2["gyro_magnitude_dps"], "node2_roll_deg": n2["roll_deg"],
        "node2_pitch_deg": n2["pitch_deg"], "node2_fsr_raw": n2["fsr_raw"],
        "node2_vibration": n2["vibration"], "node2_vibration_events": n2["vibration_events"],
    }


def run_scenario(name):
    rows = []
    start = datetime.now(timezone.utc)
    for i in range(80):
        progress = i / 79
        rows.append(packet_row(generate_gateway_packet(name, progress), start + timedelta(seconds=i * .5)))
    df = pd.DataFrame(rows)
    features = build_features(df)
    scored = score_dataframe(features)
    scored = add_temporal_evidence(scored)
    scored = add_spatial_evidence(scored)
    scored = add_sensor_health(scored)
    last = scored.iloc[-1]
    risk = calculate_risk(
        anomaly_score=float(last.anomaly_score),
        change_point_score=float(last.change_point_score),
        persistence_score=float(last.persistence_score),
        trend_score=float(last.trend_score),
        spatial_score=float(last.spatial_correlation_score),
        sensor_health_score=float(last.sensor_health_score),
        tilt_change_deg=float(last.n1_tilt),
        accel_deviation_g=float(last.n1_accel_deviation),
        vibration_events=int(last.n1_vibration_events),
        node_tilt_difference=float(last.node_tilt_difference),
        node_fsr_difference=float(last.node_fsr_difference),
        fsr_raw=float(last.n1_fsr),
        tilt_rate=float(last.n1_tilt_rate),
        fsr_change=float(last.n1_fsr_change),
        model_physics_score=float(last.physics_score),
    )
    return float(last.anomaly_score), risk["risk"], float(risk["risk_score"])


def main():
    results = {name: run_scenario(name) for name in SCENARIOS}
    print("Scenario validation")
    for name, values in results.items():
        print(f"{name:20s} anomaly={values[0]:6.2f} risk={values[1]:8s} risk_score={values[2]:6.2f}")

    assert results["NORMAL"][1] == "NORMAL", results
    assert results["GRADUAL_DEFORMATION"][1] in {"WARNING", "CRITICAL"}, results
    # A sudden isolated movement is intentionally not promoted to CRITICAL
    # without persistent/spatial corroboration.
    assert results["SUDDEN_MOVEMENT"][1] in {"WARNING", "CRITICAL"}, results
    assert results["SEVERE_EVENT"][1] == "CRITICAL", results
    assert results["NORMAL"][0] < results["SEVERE_EVENT"][0], results
    assert results["NORMAL"][2] < results["SEVERE_EVENT"][2], results
    assert results["GRADUAL_DEFORMATION"][0] > results["NORMAL"][0], results
    assert results["SUDDEN_MOVEMENT"][0] > results["NORMAL"][0], results
    print("PASS: all simulator scenarios preserve expected severity ordering.")

if __name__ == "__main__":
    main()
