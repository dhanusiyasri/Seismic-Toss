import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Notification

# Dashboard is the only real notification sink in the prototype.
# EMAIL/SMS are opt-in integrations and are never faked as successfully sent.
DEFAULT_CHANNELS = ("DASHBOARD",)
NOTIFICATION_MODE = os.getenv("NOTIFICATION_MODE", "LOCAL").upper()

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def build_notification_message(alert):
    prefix = f"[{alert.severity}] {alert.node_id}"
    if alert.event_type == "RECOVERY":
        return f"{prefix}: {alert.message}"
    return f"{prefix}: {alert.message} Risk score={float(alert.risk_score or 0):.1f}."

def _already_logged(db, alert_id, channel):
    return db.query(Notification).filter(
        Notification.alert_id == alert_id,
        Notification.channel == channel
    ).first() is not None

def dispatch_alert(db: Session, alert, channels=DEFAULT_CHANNELS):
    """Record one notification per alert/channel, with no fake external delivery."""
    results = []
    message = build_notification_message(alert)
    for channel in channels:
        channel = str(channel).upper()
        if _already_logged(db, alert.id, channel):
            continue
        if channel == "DASHBOARD":
            item = Notification(
                alert_id=alert.id, channel=channel, recipient="dashboard",
                provider="LOCAL", status="RECORDED", message=message,
                created_at=utc_now(), sent_at=utc_now()
            )
        else:
            item = Notification(
                alert_id=alert.id, channel=channel, recipient=None,
                provider="UNCONFIGURED", status="NOT_SENT", message=message,
                created_at=utc_now(),
                error="External notification provider is not configured."
            )
        db.add(item)
        results.append(item)
    db.commit()
    return results

def dispatch_alerts(db, alerts, channels=DEFAULT_CHANNELS):
    out = []
    for alert in alerts:
        out.extend(dispatch_alert(db, alert, channels))
    return out

def serialize_notification(notification):
    return {
        "id": notification.id, "alert_id": notification.alert_id,
        "channel": notification.channel, "recipient": notification.recipient,
        "provider": notification.provider, "status": notification.status,
        "message": notification.message,
        "created_at": notification.created_at.isoformat() + "Z" if notification.created_at else None,
        "sent_at": notification.sent_at.isoformat() + "Z" if notification.sent_at else None,
        "error": notification.error,
    }

def preview_notification(alert, channels=DEFAULT_CHANNELS):
    message = build_notification_message(alert)
    return [{
        "channel": str(channel).upper(), "recipient": "dashboard" if str(channel).upper() == "DASHBOARD" else None,
        "provider": "LOCAL" if str(channel).upper() == "DASHBOARD" else "UNCONFIGURED",
        "status": "PREVIEW_ONLY", "message": message,
    } for channel in channels]
