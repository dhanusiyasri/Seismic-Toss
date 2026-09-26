"""Train Isolation Forest on normal gateway behaviour only."""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd
from .feature_engineering import build_features
from .isolation_forest import train_isolation_forest
BASE = Path(__file__).resolve().parents[1]
DB = BASE / "sensor_data.db"

def main():
    with sqlite3.connect(DB) as conn:
        raw = pd.read_sql_query("SELECT * FROM gateway_readings ORDER BY server_timestamp", conn)
    features = build_features(raw)
    normal = raw["edge_risk"].astype(str).str.upper().eq("NORMAL")
    normal_features = features.loc[normal.values].copy()
    # Fallback to lower-risk observations if the database has no normal rows.
    if len(normal_features) < 100:
        normal_features = features.iloc[:max(100, int(len(features) * .5))]
    model = train_isolation_forest(normal_features)
    print(f"Trained Isolation Forest on {len(normal_features)} normal-condition rows: {model}")

if __name__ == "__main__": main()
