import math

def _safe_float(value, default=0.0):
    try:
        value=float(value); return value if math.isfinite(value) else default
    except (TypeError, ValueError): return default

def _clamp(v, lo=0.0, hi=100.0): return max(lo, min(hi, _safe_float(v)))
def _ramp(value, low, high): return _clamp((abs(_safe_float(value))-low)/max(high-low,1e-9)*100.0)

def physical_screen(tilt_change_deg=0.0, accel_deviation_g=0.0, vibration_events=0, node_tilt_difference=0.0, node_fsr_difference=0.0, fsr_raw=0.0, tilt_rate=0.0, fsr_change=0.0):
    return _clamp(0.24*_ramp(tilt_change_deg,1,8)+0.17*_ramp(accel_deviation_g,.03,.20)+0.11*_clamp(_safe_float(vibration_events)/4*100)+0.09*_ramp(node_tilt_difference,.5,5)+0.07*_ramp(node_fsr_difference,40,250)+0.08*_ramp(fsr_raw,70,450)+0.14*_ramp(tilt_rate,.05,.50)+0.10*_ramp(fsr_change,15,120))

def calculate_risk(anomaly_score=0.0, change_point_score=0.0, persistence_score=0.0, trend_score=0.0, spatial_score=0.0, sensor_health_score=100.0, tilt_change_deg=0.0, accel_deviation_g=0.0, vibration_events=0, node_tilt_difference=0.0, node_fsr_difference=0.0, fsr_raw=0.0, tilt_rate=0.0, fsr_change=0.0, model_physics_score=None, classifier_anomaly_score=0.0):
    physical=_clamp(model_physics_score if model_physics_score is not None else physical_screen(tilt_change_deg,accel_deviation_g,vibration_events,node_tilt_difference,node_fsr_difference,fsr_raw,tilt_rate,fsr_change))
    # SIH prototype fusion: unsupervised anomaly + temporal + spatial + sensor confidence.
    # Physical screen is used as a sanity gate/context, not a mine-certified threshold.
    health_factor=_clamp(sensor_health_score)
    risk_score=_clamp(0.25*_clamp(anomaly_score)+0.15*_clamp(change_point_score)+0.20*_clamp(persistence_score)+0.15*_clamp(trend_score)+0.20*_clamp(spatial_score)+0.05*health_factor)
    # Physical evidence can promote a genuinely large excursion, but poor sensor health suppresses confidence.
    risk_score=_clamp(0.90*risk_score+0.10*physical)
    if health_factor < 40: risk=min(risk_score,44.0); level="WARNING" if risk_score>=30 else "NORMAL"
    elif risk_score>=75 or (physical>=90 and (spatial_score>=70 or persistence_score>=80)): level="CRITICAL"
    elif risk_score>=50 or physical>=70 or change_point_score>=70 and persistence_score>=50: level="WARNING"
    elif risk_score>=30 or anomaly_score>=45: level="WATCH"
    else: level="NORMAL"
    evidence={"Isolation Forest":_clamp(anomaly_score),"Change point":_clamp(change_point_score),"Persistence":_clamp(persistence_score),"Trend":_clamp(trend_score),"Spatial correlation":_clamp(spatial_score),"Sensor health":health_factor,"Physics screen":physical,"Classifier context":_clamp(classifier_anomaly_score)}
    contributors=[n for n,s in sorted(evidence.items(),key=lambda x:x[1],reverse=True) if s>=40][:4]
    return {"risk":level,"risk_score":round(risk_score,2),"contributors":contributors,"physical_score":round(physical,2),"evidence":{k:round(v,2) for k,v in evidence.items()}}
