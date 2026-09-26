from datetime import datetime, timezone
from pathlib import Path
import os
import threading

import pandas as pd
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import Base, engine, get_db, SessionLocal
from models import SensorReading, GatewayReading, Alert, Notification


from ml.feature_engineering import build_features
from ml.anomaly_detector import score_dataframe
from ml.risk_engine import calculate_risk
from ml.temporal_analysis import add_temporal_evidence
from ml.spatial_analysis import add_spatial_evidence
from ml.sensor_health import add_sensor_health
from alerts.alert_manager import sync_alerts, serialize_alert
from notifications.notification_manager import dispatch_alerts, serialize_notification, preview_notification, NOTIFICATION_MODE


# Create all database tables if they do not already exist
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Runtime AI cache / background refresh
#
# Gateway ingestion must stay fast.  AI inference is therefore calculated
# asynchronously and cached in memory.  Frontend endpoints read this cache
# instead of rerunning the full ML pipeline on every poll.
# ---------------------------------------------------------------------------
AI_CACHE_LIMIT = int(os.getenv("MINEWATCH_AI_CACHE_LIMIT", "240"))
_ai_cache_lock = threading.RLock()
_ai_cache_result = pd.DataFrame()
_ai_cache_latest_id = None
_ai_refresh_running = False


def _latest_gateway_id():
    """Return the newest gateway row id using a short-lived DB session."""
    db = SessionLocal()
    try:
        latest = (
            db.query(GatewayReading.id)
            .order_by(GatewayReading.server_timestamp.desc(), GatewayReading.id.desc())
            .first()
        )
        return int(latest[0]) if latest else None
    finally:
        db.close()


def _refresh_ai_cache_worker():
    """Compute one AI snapshot in the background, then release the worker."""
    global _ai_cache_result, _ai_cache_latest_id, _ai_refresh_running

    try:
        db = SessionLocal()
        try:
            df = get_gateway_dataframe(db, limit=AI_CACHE_LIMIT)
        finally:
            db.close()

        if not df.empty:
            result = calculate_ai_for_dataframe(df)
            latest_id = int(result.iloc[-1]["id"])

            with _ai_cache_lock:
                _ai_cache_result = result.copy()
                _ai_cache_latest_id = latest_id
    except Exception as exc:
        # AI refresh must never affect gateway ingestion.
        print(f"[MineWatch AI] background refresh failed: {exc}")
    finally:
        with _ai_cache_lock:
            _ai_refresh_running = False

        # If new packets arrived while inference was running, schedule one
        # fresh snapshot.  This coalesces bursts instead of spawning one thread
        # per sensor packet.
        try:
            latest_id = _latest_gateway_id()
            with _ai_cache_lock:
                cached_id = _ai_cache_latest_id
            if latest_id is not None and latest_id != cached_id:
                _request_ai_refresh()
        except Exception as exc:
            print(f"[MineWatch AI] refresh follow-up check failed: {exc}")


def _request_ai_refresh():
    """Schedule at most one background AI computation at a time."""
    global _ai_refresh_running

    with _ai_cache_lock:
        if _ai_refresh_running:
            return
        _ai_refresh_running = True

    thread = threading.Thread(
        target=_refresh_ai_cache_worker,
        name="minewatch-ai-refresh",
        daemon=True,
    )
    thread.start()


def _get_cached_ai_result(db: Session | None = None, ensure_refresh: bool = True):
    """Return the latest cached AI dataframe without recomputing it per request."""
    with _ai_cache_lock:
        cached = _ai_cache_result.copy()
        cached_id = _ai_cache_latest_id

    if ensure_refresh:
        latest_id = None
        if db is not None:
            latest = (
                db.query(GatewayReading.id)
                .order_by(GatewayReading.server_timestamp.desc(), GatewayReading.id.desc())
                .first()
            )
            latest_id = int(latest[0]) if latest else None
        else:
            latest_id = _latest_gateway_id()

        if latest_id is not None and latest_id != cached_id:
            _request_ai_refresh()

    return cached


app = FastAPI(
    title="Mine Subsidence Monitoring API",
    version="2.0.0"
)


@app.on_event("startup")
def warm_ai_cache():
    """Warm the AI cache without delaying FastAPI startup."""
    _request_ai_refresh()


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# PYDANTIC MODELS
# ============================================================

class SensorData(BaseModel):
    node_id: str
    timestamp: datetime

    accel_mean_g: float = 0
    accel_rms_g: float = 0
    accel_peak_g: float = 0

    gyro_mean_dps: float = 0
    gyro_peak_dps: float = 0

    roll_change_deg: float = 0
    pitch_change_deg: float = 0
    tilt_change_deg: float = 0

    fsr_mean: float = 0
    fsr_min: float = 0
    fsr_max: float = 0
    fsr_std: float = 0
    fsr_rate_peak: float = 0

    vibration_events: int = 0
    vibration_duration_ms: int = 0

    shock_detected: bool = False
    vibration_detected: bool = False
    tilt_detected: bool = False
    pressure_detected: bool = False
    sudden_pressure_detected: bool = False


class Node1Data(BaseModel):
    accel_x_g: float = 0
    accel_y_g: float = 0
    accel_z_g: float = 0
    accel_magnitude_g: float = 0

    gyro_x_dps: float = 0
    gyro_y_dps: float = 0
    gyro_z_dps: float = 0
    gyro_magnitude_dps: float = 0

    roll_deg: float = 0
    pitch_deg: float = 0

    fsr_raw: float = 0
    fsr_voltage: float = 0
    fsr_resistance_ohm: float = 0

    vibration: bool = False
    vibration_events: int = 0
    vibration_duration_ms: int = 0

    tilt_change_deg: float = 0
    accel_deviation_g: float = 0


class GatewayStatus(BaseModel):
    node2_online: bool = False
    sd_available: bool = False
    esp_now_available: bool = False


class Node2Data(BaseModel):
    status: str = "OFFLINE"

    packet_id: int | None = None
    timestamp_ms: int | None = None

    accel_x_g: float = 0
    accel_y_g: float = 0
    accel_z_g: float = 0
    accel_magnitude_g: float = 0

    gyro_x_dps: float = 0
    gyro_y_dps: float = 0
    gyro_z_dps: float = 0
    gyro_magnitude_dps: float = 0

    roll_deg: float = 0
    pitch_deg: float = 0

    fsr_raw: float = 0
    fsr_voltage: float = 0
    fsr_resistance_ohm: float = 0

    vibration: bool = False
    vibration_events: int = 0


class GatewayPacket(BaseModel):
    timestamp_ms: int = 0
    risk: str = "NORMAL"

    node1: Node1Data
    gateway: GatewayStatus
    node2: Node2Data


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def utc_now():
    """Return the current UTC time in SQLite's timezone-naive format."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_isoformat(value) -> str:
    """Serialize a database or pandas timestamp as a single UTC ISO-8601 value."""
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def gateway_reading_to_row(reading):
    """
    Convert a GatewayReading database record into the
    dataframe format expected by the ML feature pipeline.
    """

    return {
        "id": reading.id,
        "server_timestamp": reading.server_timestamp,
        "device_timestamp_ms": reading.device_timestamp_ms,
        "edge_risk": reading.edge_risk,

        # ---------------- NODE 1 ----------------
        "node1_accel_x_g": reading.node1_accel_x_g,
        "node1_accel_y_g": reading.node1_accel_y_g,
        "node1_accel_z_g": reading.node1_accel_z_g,
        "node1_accel_magnitude_g": reading.node1_accel_magnitude_g,

        "node1_gyro_x_dps": reading.node1_gyro_x_dps,
        "node1_gyro_y_dps": reading.node1_gyro_y_dps,
        "node1_gyro_z_dps": reading.node1_gyro_z_dps,
        "node1_gyro_magnitude_dps": reading.node1_gyro_magnitude_dps,

        "node1_roll_deg": reading.node1_roll_deg,
        "node1_pitch_deg": reading.node1_pitch_deg,

        "node1_fsr_raw": reading.node1_fsr_raw,
        "node1_fsr_voltage": reading.node1_fsr_voltage,
        "node1_fsr_resistance_ohm": reading.node1_fsr_resistance_ohm,

        "node1_vibration": reading.node1_vibration,
        "node1_vibration_events": reading.node1_vibration_events,
        "node1_vibration_duration_ms": reading.node1_vibration_duration_ms,

        "node1_tilt_change_deg": reading.node1_tilt_change_deg,
        "node1_accel_deviation_g": reading.node1_accel_deviation_g,

        # ---------------- GATEWAY ----------------
        "node2_online": reading.node2_online,
        "sd_available": reading.sd_available,
        "esp_now_available": reading.esp_now_available,

        # ---------------- NODE 2 ----------------
        "node2_timestamp_ms": None,

        "node2_accel_x_g": reading.node2_accel_x_g,
        "node2_accel_y_g": reading.node2_accel_y_g,
        "node2_accel_z_g": reading.node2_accel_z_g,
        "node2_accel_magnitude_g": reading.node2_accel_magnitude_g,

        "node2_gyro_x_dps": reading.node2_gyro_x_dps,
        "node2_gyro_y_dps": reading.node2_gyro_y_dps,
        "node2_gyro_z_dps": reading.node2_gyro_z_dps,
        "node2_gyro_magnitude_dps": reading.node2_gyro_magnitude_dps,

        "node2_roll_deg": reading.node2_roll_deg,
        "node2_pitch_deg": reading.node2_pitch_deg,

        "node2_fsr_raw": reading.node2_fsr_raw,
        "node2_fsr_voltage": reading.node2_fsr_voltage,
        "node2_fsr_resistance_ohm": reading.node2_fsr_resistance_ohm,

        "node2_vibration": reading.node2_vibration,
        "node2_vibration_events": reading.node2_vibration_events,
    }


def get_gateway_dataframe(db: Session, limit: int | None = None):
    """
    Load gateway readings from database and convert to dataframe.
    """

    query = db.query(GatewayReading).order_by(GatewayReading.server_timestamp.desc())
    if limit:
        query = query.limit(max(1, int(limit)))
    readings = list(reversed(query.all()))

    if not readings:
        return pd.DataFrame()

    rows = [
        gateway_reading_to_row(reading)
        for reading in readings
    ]

    return pd.DataFrame(rows)


def calculate_ai_for_dataframe(df):
    """
    Complete AI pipeline:

        Gateway data → time-aware features → calibrated class probabilities
        → independent physical screen → authoritative risk fusion.
    """

    if df.empty:
        return df.copy()

    # ---------------------------------------------------------
    # STEP 1: Feature engineering
    # ---------------------------------------------------------

    features = build_features(df)

    # ---------------------------------------------------------
    # STEP 2: AI anomaly detection
    # ---------------------------------------------------------

    scored = score_dataframe(features)
    # Temporal, spatial and sensor-health evidence are derived after ML scoring.
    scored = add_temporal_evidence(scored)
    scored = add_spatial_evidence(scored)
    scored = add_sensor_health(scored)

    result = scored.copy()

    # ---------------------------------------------------------
    # STEP 3: Risk calculation
    # ---------------------------------------------------------

    risks = []

    for _, row in result.iterrows():

        def safe_float(column, default=0.0):
            value = row.get(column, default)

            try:
                if pd.isna(value):
                    return default

                return float(value)

            except (TypeError, ValueError):
                return default

        def safe_int(column, default=0):
            value = row.get(column, default)

            try:
                if pd.isna(value):
                    return default

                return int(value)

            except (TypeError, ValueError):
                return default

        risk = calculate_risk(
            anomaly_score=safe_float("anomaly_score"),
            change_point_score=safe_float("change_point_score"),
            persistence_score=safe_float("persistence_score"),
            trend_score=safe_float("trend_score"),
            spatial_score=safe_float("spatial_correlation_score"),
            sensor_health_score=safe_float("sensor_health_score", 100.0),

            tilt_change_deg=safe_float(
                "node1_tilt_change_deg"
            ),

            accel_deviation_g=safe_float(
                "node1_accel_deviation_g"
            ),

            vibration_events=safe_int(
                "node1_vibration_events"
            ),

            node_tilt_difference=safe_float(
                "node_tilt_difference"
            ),

            node_fsr_difference=safe_float(
                "node_fsr_difference"
            ),

            fsr_raw=safe_float(
                "node1_fsr_raw"
            ),
            tilt_rate=safe_float("n1_tilt_rate"),
            fsr_change=safe_float("n1_fsr_change"),
            model_physics_score=safe_float("physics_score"),
            classifier_anomaly_score=safe_float("classifier_anomaly_score")
        )

        risks.append(risk)

    # ---------------------------------------------------------
    # STEP 4: Add risk results
    # ---------------------------------------------------------

    result["ai_risk"] = [
        risk["risk"]
        for risk in risks
    ]

    result["risk_score"] = [
        float(risk["risk_score"])
        for risk in risks
    ]

    result["contributors"] = [
        risk["contributors"]
        for risk in risks
    ]

    result["physical_score"] = [
        float(risk.get("physical_score", 0.0))
        for risk in risks
    ]

    return result


# ============================================================
# BASIC HEALTH CHECK
# ============================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Mine Subsidence Monitoring API",
        "version": "2.0.0"
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ml": "temperature-scaled",
        "model": "temperature-scaled multiclass logistic regression + independent engineering screen",
        "probability_calibrated": True,
        "field_calibrated": False,
        "offline_inference_artifact": True,
        "alert_state_machine": True
    }


# ============================================================
# OLD SENSOR API
# ============================================================

@app.post("/api/sensor-data")
def receive_sensor_data(
    data: SensorData,
    db: Session = Depends(get_db)
):

    reading = SensorReading(
        node_id=data.node_id,
        timestamp=data.timestamp,

        accel_mean_g=data.accel_mean_g,
        accel_rms_g=data.accel_rms_g,
        accel_peak_g=data.accel_peak_g,

        gyro_mean_dps=data.gyro_mean_dps,
        gyro_peak_dps=data.gyro_peak_dps,

        roll_change_deg=data.roll_change_deg,
        pitch_change_deg=data.pitch_change_deg,
        tilt_change_deg=data.tilt_change_deg,

        fsr_mean=data.fsr_mean,
        fsr_min=data.fsr_min,
        fsr_max=data.fsr_max,
        fsr_std=data.fsr_std,
        fsr_rate_peak=data.fsr_rate_peak,

        vibration_events=data.vibration_events,
        vibration_duration_ms=data.vibration_duration_ms,

        shock_detected=data.shock_detected,
        vibration_detected=data.vibration_detected,
        tilt_detected=data.tilt_detected,
        pressure_detected=data.pressure_detected,
        sudden_pressure_detected=data.sudden_pressure_detected,
    )

    db.add(reading)
    db.commit()
    db.refresh(reading)

    return {
        "status": "success",
        "id": reading.id
    }


# ============================================================
# GATEWAY API
# ============================================================

@app.post("/api/gateway-data")
def receive_gateway_data(
    data: GatewayPacket,
    db: Session = Depends(get_db)
):

    reading = GatewayReading(

        server_timestamp=utc_now(),

        device_timestamp_ms=data.timestamp_ms,

        edge_risk=data.risk,

        # ---------------- NODE 1 ----------------

        node1_accel_x_g=data.node1.accel_x_g,
        node1_accel_y_g=data.node1.accel_y_g,
        node1_accel_z_g=data.node1.accel_z_g,
        node1_accel_magnitude_g=data.node1.accel_magnitude_g,

        node1_gyro_x_dps=data.node1.gyro_x_dps,
        node1_gyro_y_dps=data.node1.gyro_y_dps,
        node1_gyro_z_dps=data.node1.gyro_z_dps,
        node1_gyro_magnitude_dps=data.node1.gyro_magnitude_dps,

        node1_roll_deg=data.node1.roll_deg,
        node1_pitch_deg=data.node1.pitch_deg,

        node1_fsr_raw=data.node1.fsr_raw,
        node1_fsr_voltage=data.node1.fsr_voltage,
        node1_fsr_resistance_ohm=data.node1.fsr_resistance_ohm,

        node1_vibration=data.node1.vibration,
        node1_vibration_events=data.node1.vibration_events,
        node1_vibration_duration_ms=data.node1.vibration_duration_ms,

        node1_tilt_change_deg=data.node1.tilt_change_deg,
        node1_accel_deviation_g=data.node1.accel_deviation_g,

        # ---------------- GATEWAY ----------------

        node2_online=data.gateway.node2_online,
        sd_available=data.gateway.sd_available,
        esp_now_available=data.gateway.esp_now_available,

        # ---------------- NODE 2 ----------------

    

        node2_accel_x_g=data.node2.accel_x_g,
        node2_accel_y_g=data.node2.accel_y_g,
        node2_accel_z_g=data.node2.accel_z_g,
        node2_accel_magnitude_g=data.node2.accel_magnitude_g,

        node2_gyro_x_dps=data.node2.gyro_x_dps,
        node2_gyro_y_dps=data.node2.gyro_y_dps,
        node2_gyro_z_dps=data.node2.gyro_z_dps,
        node2_gyro_magnitude_dps=data.node2.gyro_magnitude_dps,

        node2_roll_deg=data.node2.roll_deg,
        node2_pitch_deg=data.node2.pitch_deg,

        node2_fsr_raw=data.node2.fsr_raw,
        node2_fsr_voltage=data.node2.fsr_voltage,
        node2_fsr_resistance_ohm=data.node2.fsr_resistance_ohm,

        node2_vibration=data.node2.vibration,
        node2_vibration_events=data.node2.vibration_events,
    )

    db.add(reading)
    db.commit()
    db.refresh(reading)

    # Never run the expensive AI pipeline inside the ingestion request.
    # The simulator/ESP32 receives its acknowledgement immediately.
    _request_ai_refresh()

    return {
        "status": "success",
        "id": reading.id,
        "edge_risk": data.risk,
        "ai_status": "BACKGROUND"
    }


# ============================================================
# LATEST SENSOR DATA
# ============================================================

@app.get("/api/sensors/latest")
def latest_sensors(
    db: Session = Depends(get_db)
):

    gateway = (
        db.query(GatewayReading)
        .order_by(GatewayReading.server_timestamp.desc())
        .first()
    )

    if not gateway:
        return []

    timestamp = gateway.server_timestamp

    result = []

    # ---------------- NODE 1 ----------------

    result.append({
        "id": gateway.id,
        "node_id": "NODE_01",
        "timestamp": utc_isoformat(timestamp),

        "accel_peak_g": gateway.node1_accel_magnitude_g,
        "gyro_peak_dps": gateway.node1_gyro_magnitude_dps,

        "roll_change_deg": gateway.node1_roll_deg,
        "pitch_change_deg": gateway.node1_pitch_deg,
        "tilt_change_deg": gateway.node1_tilt_change_deg,

        "fsr_mean": gateway.node1_fsr_raw,
        "fsr_min": gateway.node1_fsr_raw,
        "fsr_max": gateway.node1_fsr_raw,

        "vibration_events": gateway.node1_vibration_events,
        "vibration_duration_ms":
            gateway.node1_vibration_duration_ms,

        "shock_detected":
            abs(gateway.node1_accel_deviation_g) >= 0.20,

        "vibration_detected":
            gateway.node1_vibration,

        "tilt_detected":
            gateway.node1_tilt_change_deg >= 8.0,

        "pressure_detected":
            gateway.node1_fsr_raw > 0,

        "sudden_pressure_detected": False,

        "risk": gateway.edge_risk
    })

    # ---------------- NODE 2 ----------------

    if gateway.node2_online:

        result.append({
            "id": gateway.id,
            "node_id": "NODE_02",
            "timestamp": utc_isoformat(timestamp),

            "accel_peak_g":
                gateway.node2_accel_magnitude_g,

            "gyro_peak_dps":
                gateway.node2_gyro_magnitude_dps,

            "roll_change_deg":
                gateway.node2_roll_deg,

            "pitch_change_deg":
                gateway.node2_pitch_deg,

            "tilt_change_deg":
                max(
                    abs(gateway.node2_roll_deg),
                    abs(gateway.node2_pitch_deg)
                ),

            "fsr_mean":
                gateway.node2_fsr_raw,

            "fsr_min":
                gateway.node2_fsr_raw,

            "fsr_max":
                gateway.node2_fsr_raw,

            "vibration_events":
                gateway.node2_vibration_events,

            "vibration_duration_ms": 0,

            "shock_detected": False,

            "vibration_detected":
                gateway.node2_vibration,

            "tilt_detected":
                max(
                    abs(gateway.node2_roll_deg),
                    abs(gateway.node2_pitch_deg)
                ) >= 8.0,

            "pressure_detected":
                gateway.node2_fsr_raw > 0,

            "sudden_pressure_detected": False,

            "risk": gateway.edge_risk
        })

    return result


# ============================================================
# SENSOR HISTORY
# ============================================================

@app.get("/api/sensors/history/{node_id}")
def sensor_history(
    node_id: str,
    db: Session = Depends(get_db)
):

    readings = (
        db.query(GatewayReading)
        .order_by(GatewayReading.server_timestamp.asc())
        .all()
    )

    result = []

    for reading in readings:

        timestamp = reading.server_timestamp

        if node_id == "NODE_01":

            result.append({
                "id": reading.id,
                "node_id": "NODE_01",
                "timestamp": utc_isoformat(timestamp),

                "accel_peak_g":
                    reading.node1_accel_magnitude_g,

                "gyro_peak_dps":
                    reading.node1_gyro_magnitude_dps,

                "roll_change_deg":
                    reading.node1_roll_deg,

                "pitch_change_deg":
                    reading.node1_pitch_deg,

                "tilt_change_deg":
                    reading.node1_tilt_change_deg,

                "fsr_mean":
                    reading.node1_fsr_raw,

                "vibration_events":
                    reading.node1_vibration_events,

                "risk":
                    reading.edge_risk
            })

        elif node_id == "NODE_02" and reading.node2_online:

            result.append({
                "id": reading.id,
                "node_id": "NODE_02",
                "timestamp": utc_isoformat(timestamp),

                "accel_peak_g":
                    reading.node2_accel_magnitude_g,

                "gyro_peak_dps":
                    reading.node2_gyro_magnitude_dps,

                "roll_change_deg":
                    reading.node2_roll_deg,

                "pitch_change_deg":
                    reading.node2_pitch_deg,

                "tilt_change_deg":
                    max(
                        abs(reading.node2_roll_deg),
                        abs(reading.node2_pitch_deg)
                    ),

                "fsr_mean":
                    reading.node2_fsr_raw,

                "vibration_events":
                    reading.node2_vibration_events,

                "risk":
                    reading.edge_risk
            })

    return result


# ============================================================
# GIS CONFIGURATION
# ============================================================

# Coordinates are intentionally configurable. The fallback values are
# demo coordinates only and must be replaced with the actual mine/node
# coordinates before field deployment.
GIS_MINE_LAT = float(os.getenv("MINE_LAT", "20.000000"))
GIS_MINE_LON = float(os.getenv("MINE_LON", "80.000000"))
GIS_NODE_OFFSET = float(os.getenv("MINE_NODE_OFFSET", "0.001000"))
GIS_USING_DEMO_COORDINATES = (
    "MINE_LAT" not in os.environ or "MINE_LON" not in os.environ
)


# ============================================================
# GIS OVERVIEW
# ============================================================

@app.get("/api/gis/nodes")
def gis_nodes(
    db: Session = Depends(get_db)
):
    """
    Return map-ready monitoring-node data.

    GIS consumes the existing AI/risk result; it does not run a
    separate anomaly model. Coordinates are configuration values.
    """

    df = get_gateway_dataframe(db, limit=120)

    if df.empty:
        return {
            "site": {
                "latitude": GIS_MINE_LAT,
                "longitude": GIS_MINE_LON,
                "risk": "NO_DATA",
                "risk_score": 0,
            },
            "nodes": [],
            "using_demo_coordinates": GIS_USING_DEMO_COORDINATES,
        }

    ai_result = _get_cached_ai_result(db)
    if ai_result.empty:
        _request_ai_refresh()
        latest_gateway = (
            db.query(GatewayReading)
            .order_by(GatewayReading.server_timestamp.desc())
            .first()
        )
        if not latest_gateway:
            return {
                "site": {
                    "latitude": GIS_MINE_LAT,
                    "longitude": GIS_MINE_LON,
                    "risk": "NO_DATA",
                    "risk_score": 0,
                },
                "nodes": [],
                "using_demo_coordinates": GIS_USING_DEMO_COORDINATES,
            }
        site_risk = str(latest_gateway.edge_risk or "NORMAL")
        risk_score = 0.0
        last_seen = utc_isoformat(latest_gateway.server_timestamp)
        node2_online = bool(latest_gateway.node2_online)
    else:
        latest_ai = ai_result.iloc[-1]
        site_risk = str(latest_ai.get("ai_risk", "NORMAL"))
        risk_score = float(latest_ai.get("risk_score", 0) or 0)
        latest_gateway = (
            db.query(GatewayReading)
            .order_by(GatewayReading.server_timestamp.desc())
            .first()
        )
        last_seen = utc_isoformat(latest_gateway.server_timestamp)
        node2_online = bool(latest_gateway.node2_online)

    nodes = [
        {
            "node_id": "NODE_01",
            "latitude": GIS_MINE_LAT,
            "longitude": GIS_MINE_LON,
            "status": "ONLINE",
            "last_seen": last_seen,
            "site_risk": site_risk,
            "risk_score": risk_score,
            "risk_scope": "SITE",
        },
        {
            "node_id": "NODE_02",
            "latitude": GIS_MINE_LAT + GIS_NODE_OFFSET,
            "longitude": GIS_MINE_LON + GIS_NODE_OFFSET,
            "status": "ONLINE" if node2_online else "OFFLINE",
            "last_seen": last_seen,
            "site_risk": site_risk,
            "risk_score": risk_score,
            "risk_scope": "SITE",
        },
    ]

    return {
        "site": {
            "latitude": GIS_MINE_LAT,
            "longitude": GIS_MINE_LON,
            "risk": site_risk,
            "risk_score": risk_score,
            "last_seen": last_seen,
        },
        "nodes": nodes,
        "using_demo_coordinates": GIS_USING_DEMO_COORDINATES,
    }


# ============================================================
# NODE STATUS
# ============================================================

@app.get("/api/nodes")
def get_nodes(
    db: Session = Depends(get_db)
):

    latest = (
        db.query(GatewayReading)
        .order_by(GatewayReading.server_timestamp.desc())
        .first()
    )

    if not latest:
        return []

    nodes = [
        {
            "node_id": "NODE_01",
            "status": "ONLINE",
            "last_seen": utc_isoformat(latest.server_timestamp)
        }
    ]

    if latest.node2_online:

        nodes.append({
            "node_id": "NODE_02",
            "status": "ONLINE",
            "last_seen": utc_isoformat(latest.server_timestamp)
        })

    return nodes


# ============================================================
# GATEWAY LATEST
# ============================================================

@app.get("/api/gateway/latest")
def gateway_latest(
    db: Session = Depends(get_db)
):

    reading = (
        db.query(GatewayReading)
        .order_by(GatewayReading.server_timestamp.desc())
        .first()
    )

    if not reading:
        raise HTTPException(
            status_code=404,
            detail="No gateway data available"
        )

    return {
        "id": reading.id,

        "timestamp": utc_isoformat(reading.server_timestamp),

        "device_timestamp_ms":
            reading.device_timestamp_ms,

        "edge_risk":
            reading.edge_risk,

        "node2_online":
            reading.node2_online,

        "sd_available":
            reading.sd_available,

        "esp_now_available":
            reading.esp_now_available
    }


# ============================================================
# AI LATEST
# ============================================================

@app.get("/api/ai/latest")
def ai_latest(
    db: Session = Depends(get_db)
):

    df = get_gateway_dataframe(db, limit=120)

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail="No gateway data available"
        )

    result = _get_cached_ai_result(db)
    if result.empty:
        _request_ai_refresh()
        raise HTTPException(status_code=503, detail="AI model is initializing; retry shortly.")

    row = result.iloc[-1]

    return {
        "timestamp": utc_isoformat(row["server_timestamp"]),

        "anomaly_score":
            float(row["anomaly_score"]),

        "anomaly_label":
            str(row["anomaly_label"]),

        "risk":
            str(row["ai_risk"]),

        "risk_score":
            float(row["risk_score"]),

        "model_confidence":
            float(row.get("model_confidence", 0.0)),

        "physics_score":
            float(row.get("physics_score", 0.0)),

        "decision_margin": float(row.get("decision_margin", 0.0)),
        "change_point_score": float(row.get("change_point_score", 0.0)),
        "persistence_score": float(row.get("persistence_score", 0.0)),
        "trend_score": float(row.get("trend_score", 0.0)),
        "spatial_correlation_score": float(row.get("spatial_correlation_score", 0.0)),
        "sensor_health_score": float(row.get("sensor_health_score", 100.0)),
        "sensor_health_status": str(row.get("sensor_health_status", "HEALTHY")),
        "evidence": {},

        "probabilities": {
            "NORMAL": float(row.get("prob_normal", 0.0)),
            "WARNING": float(row.get("prob_warning", 0.0)),
            "CRITICAL": float(row.get("prob_critical", 0.0)),
        },

        "contributors":
            row["contributors"]
    }


# ============================================================
# ALERTS
# ============================================================

def _current_ai_state(db: Session):
    """Calculate the current site AI/risk state for alert synchronization."""

    df = get_gateway_dataframe(db, limit=120)

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail="No gateway data available"
        )

    result = _get_cached_ai_result(db)
    if result.empty:
        _request_ai_refresh()
        raise HTTPException(status_code=503, detail="AI model is initializing; retry shortly.")

    latest_ai = result.iloc[-1]

    latest_gateway = (
        db.query(GatewayReading)
        .order_by(GatewayReading.server_timestamp.desc())
        .first()
    )

    return latest_ai, latest_gateway


@app.get("/api/alerts")
def get_alerts(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Return recent alerts after synchronizing the current monitoring state."""

    limit = max(1, min(limit, 200))
    latest_ai, latest_gateway = _current_ai_state(db)
    current_alerts = sync_alerts(
        db,
        ai_result=latest_ai,
        latest_gateway=latest_gateway,
    )
    dispatch_alerts(db, current_alerts)

    alerts = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )

    return [serialize_alert(alert) for alert in alerts]


@app.get("/api/alerts/latest")
def get_latest_alert(
    db: Session = Depends(get_db)
):
    """Synchronize and return the latest alert/recovery record."""

    latest_ai, latest_gateway = _current_ai_state(db)
    current_alerts = sync_alerts(
        db,
        ai_result=latest_ai,
        latest_gateway=latest_gateway,
    )
    dispatch_alerts(db, current_alerts)

    alert = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .first()
    )

    if not alert:
        return None

    return serialize_alert(alert)


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if not alert.acknowledged:
        alert.acknowledged = True
        alert.acknowledged_at = utc_now()
        db.commit()
        db.refresh(alert)

    return serialize_alert(alert)


@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.resolved:
        return serialize_alert(alert)
    raise HTTPException(
        status_code=409,
        detail="Alert recovery is automatic; acknowledge the event instead of manually resolving it."
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.get("/api/notifications")
def get_notifications(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Return notification delivery logs."""

    limit = max(1, min(limit, 200))
    notifications = (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [serialize_notification(item) for item in notifications]


@app.get("/api/notifications/mode")
def get_notification_mode():
    """Show whether the notification layer is running in safe MOCK mode."""
    return {
        "mode": NOTIFICATION_MODE,
        "external_messages_enabled": False,
        "note": "This prototype does not send real email/SMS messages."
    }


@app.post("/api/notifications/preview")
def preview_notifications(
    db: Session = Depends(get_db)
):
    """Side-effect-free notification preview using the current latest alert."""

    alert = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="No alerts available for preview")

    return {
        "alert": serialize_alert(alert),
        "notifications": preview_notification(alert),
    }


# ============================================================
# AI HISTORY
# ============================================================

@app.get("/api/ai/history")
def ai_history(
    db: Session = Depends(get_db)
):

    result = _get_cached_ai_result(db)

    if result.empty:
        return []

    history = []

    for _, row in result.iterrows():

        history.append({
            "timestamp": utc_isoformat(row["server_timestamp"]),

            "anomaly_score":
                float(row["anomaly_score"]),

            "risk_score":
                float(row["risk_score"]),

            "risk":
                str(row["ai_risk"]),

            "anomaly_label":
                str(row["anomaly_label"]),

            "model_confidence":
                float(row.get("model_confidence", 0.0)),

            "physics_score":
                float(row.get("physics_score", 0.0)),

            "decision_margin": float(row.get("decision_margin", 0.0)),
            "change_point_score": float(row.get("change_point_score", 0.0)),
            "persistence_score": float(row.get("persistence_score", 0.0)),
            "trend_score": float(row.get("trend_score", 0.0)),
            "spatial_correlation_score": float(row.get("spatial_correlation_score", 0.0)),
            "sensor_health_score": float(row.get("sensor_health_score", 100.0)),
            "sensor_health_status": str(row.get("sensor_health_status", "HEALTHY"))
        })

    return history


# ============================================================
# AI SUMMARY
# ============================================================

@app.get("/api/ai/summary")
def ai_summary(
    db: Session = Depends(get_db)
):

    result = _get_cached_ai_result(db)

    if result.empty:
        return {
            "status": "AI_INITIALIZING",
            "total_records": 0
        }

    latest = result.iloc[-1]

    return {
        "status": "OK",

        "total_records":
            len(result),

        "window_records":
            len(result),

        "latest_anomaly_score":
            float(latest["anomaly_score"]),

        "latest_risk_score":
            float(latest["risk_score"]),

        "latest_risk":
            str(latest["ai_risk"]),

        "latest_model_confidence":
            float(latest.get("model_confidence", 0.0)),

        "latest_physics_score":
            float(latest.get("physics_score", 0.0)),

        "model": "Isolation Forest + change-point detection + temporal persistence + spatial correlation + sensor health + physics-informed risk fusion",

        "anomalies":
            int(
                (result["anomaly_label"] == "ANOMALY")
                .sum()
            ),

        "critical":
            int(
                (result["ai_risk"] == "CRITICAL")
                .sum()
            ),

        "warning":
            int(
                (result["ai_risk"] == "WARNING")
                .sum()
            ),

        "normal": int((result["ai_risk"] == "NORMAL").sum()),
        "watch": int((result["ai_risk"] == "WATCH").sum())
    }
