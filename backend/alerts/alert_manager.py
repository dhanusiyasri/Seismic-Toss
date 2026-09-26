import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Alert, MonitoringState

SEVERITY_ORDER = {"NORMAL": 0, "WARNING": 1, "OFFLINE": 2, "CRITICAL": 3}
ACTIVE_LEVELS = {"WATCH", "WARNING", "CRITICAL", "OFFLINE"}
ACTIVATE_SAMPLES = 2
RECOVER_SAMPLES = 3

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _create_alert(db: Session, *, node_id, level, event_type, message,
                  risk_score=0.0, anomaly_score=0.0, contributors=None,
                  previous_level=None, timestamp=None, resolved=False,
                  acknowledged=False):
    now = timestamp or utc_now()
    alert = Alert(
        node_id=node_id, severity=level, event_type=event_type, message=message,
        risk_score=float(risk_score), anomaly_score=float(anomaly_score),
        contributors_json=json.dumps(contributors or []), previous_severity=previous_level,
        created_at=now, acknowledged=acknowledged, resolved=resolved,
        resolved_at=now if resolved else None,
    )
    db.add(alert); db.flush(); return alert

def _open(db, key):
    return (db.query(Alert).filter(Alert.node_id == key, Alert.resolved.is_(False))
            .order_by(Alert.created_at.desc()).first())

def _state(db, key, fallback="NORMAL"):
    state = db.query(MonitoringState).filter(MonitoringState.key == key).first()
    if state is None:
        current = _open(db, key)
        state = MonitoringState(
            key=key, stable_severity=current.severity if current else fallback,
            candidate_severity=current.severity if current else fallback,
            candidate_count=0, updated_at=utc_now())
        db.add(state); db.flush()
    return state

def _close(alert, when):
    alert.resolved = True
    alert.resolved_at = when

def _site_message(level, score):
    return {
        "CRITICAL": f"Critical site risk detected (risk score {score:.1f}).",
        "WARNING": f"Warning site risk detected (risk score {score:.1f}).",
        "WATCH": f"Watch-level site anomaly detected (risk score {score:.1f}).",
    }.get(level, "Site risk returned to normal.")

def _transition(db, *, key, level, message, risk_score, anomaly_score, contributors, timestamp,
                activation_samples=ACTIVATE_SAMPLES, recovery_samples=RECOVER_SAMPLES,
                immediate=False):
    state = _state(db, key)
    current = _open(db, key)
    stable = state.stable_severity

    # Escalation may be immediate only when a hard critical gate is met.
    if level in ACTIVE_LEVELS and immediate:
        state.candidate_severity, state.candidate_count = level, activation_samples
    elif level == stable:
        state.candidate_severity, state.candidate_count = level, 0
        return []
    else:
        if state.candidate_severity == level:
            state.candidate_count += 1
        else:
            state.candidate_severity, state.candidate_count = level, 1
        needed = recovery_samples if level == "NORMAL" else activation_samples
        if state.candidate_count < needed:
            state.updated_at = timestamp
            return []

    previous = stable
    state.stable_severity = level
    state.candidate_severity = level
    state.candidate_count = 0
    state.updated_at = timestamp

    created = []
    if current:
        _close(current, timestamp)

    if level in ACTIVE_LEVELS:
        event = "ESCALATION" if SEVERITY_ORDER[level] > SEVERITY_ORDER.get(previous, 0) and previous != "NORMAL" else ("ESCALATION" if previous != "NORMAL" else "ALERT")
        created.append(_create_alert(db, node_id=key, level=level, event_type=event, message=message,
                                     risk_score=risk_score, anomaly_score=anomaly_score,
                                     contributors=contributors, previous_level=previous if previous != level else None,
                                     timestamp=timestamp))
    elif previous in ACTIVE_LEVELS:
        created.append(_create_alert(
            db, node_id=key, level="NORMAL", event_type="RECOVERY",
            message=f"{key.replace('_', ' ').title()} recovered from {previous} to NORMAL.",
            risk_score=risk_score, anomaly_score=anomaly_score, contributors=contributors,
            previous_level=previous, timestamp=timestamp, resolved=True, acknowledged=True))
    return created

def sync_alerts(db: Session, *, ai_result, latest_gateway):
    """Synchronize authoritative site and communication state with debounce/hysteresis."""
    if ai_result is None or latest_gateway is None:
        return []

    timestamp = latest_gateway.server_timestamp or utc_now()
    risk = str(ai_result.get("ai_risk", "NORMAL")).upper()
    risk_score = float(ai_result.get("risk_score", 0) or 0)
    anomaly_score = float(ai_result.get("anomaly_score", 0) or 0)
    contributors = ai_result.get("contributors", []) or []

    # Critical physical excursions are immediate; ordinary state changes require confirmation.
    immediate_critical = risk == "CRITICAL" and (risk_score >= 90 or anomaly_score >= 95)
    created = _transition(
        db, key="MINE_SITE", level=risk, message=_site_message(risk, risk_score),
        risk_score=risk_score, anomaly_score=anomaly_score, contributors=contributors,
        timestamp=timestamp, immediate=immediate_critical)

    online = bool(latest_gateway.node2_online)
    created += _transition(
        db, key="NODE_02", level="NORMAL" if online else "OFFLINE",
        message="Node 2 communication is offline." if not online else "Node 2 communication recovered.",
        risk_score=risk_score, anomaly_score=anomaly_score,
        contributors=["Node 2 communication"] if not online else ["Node 2 communication recovered"],
        timestamp=timestamp)

    db.commit()
    return created

def serialize_alert(alert):
    try: contributors = json.loads(alert.contributors_json or "[]")
    except (TypeError, json.JSONDecodeError): contributors = []
    return {
        "id": alert.id, "node_id": alert.node_id, "severity": alert.severity,
        "event_type": alert.event_type, "message": alert.message,
        "risk_score": float(alert.risk_score or 0), "anomaly_score": float(alert.anomaly_score or 0),
        "contributors": contributors, "previous_severity": alert.previous_severity,
        "created_at": alert.created_at.isoformat() + "Z" if alert.created_at else None,
        "acknowledged": bool(alert.acknowledged),
        "acknowledged_at": alert.acknowledged_at.isoformat() + "Z" if alert.acknowledged_at else None,
        "resolved": bool(alert.resolved),
        "resolved_at": alert.resolved_at.isoformat() + "Z" if alert.resolved_at else None,
    }
