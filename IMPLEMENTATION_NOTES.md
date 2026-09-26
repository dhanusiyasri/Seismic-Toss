# MineWatch – SIH Hybrid Early-Warning Upgrade

This version upgrades the runtime intelligence layer around the existing MineWatch application.

## Runtime pipeline

1. Feature engineering from gateway readings.
2. Isolation Forest trained on normal-condition gateway behaviour.
3. Calibrated classifier retained as secondary contextual evidence.
4. Page-Hinkley change-point evidence.
5. Temporal persistence and anomaly trend.
6. Multi-node spatial correlation: both nodes must show elevated risk signals before spatial evidence is counted.
7. Sensor/data-health confidence.
8. Risk fusion into `NORMAL`, `WATCH`, `WARNING`, or `CRITICAL`.
9. Existing alert state machine and dashboard consume the final risk.

## Fusion weights

- Isolation Forest: 25%
- Change point: 15%
- Persistence: 20%
- Trend: 15%
- Spatial correlation: 20%
- Sensor health: 5%
- Physics-informed screen: 10% secondary sanity/context contribution

These are prototype engineering weights, not mine-specific statutory or geotechnical safety limits.

## Training

`backend/ml/train_isolation_forest.py` trains the Isolation Forest using rows labelled `NORMAL` by the existing simulator/edge-risk stream. The generated artifact is stored under `backend/ml/artifacts/`.

The calibrated classifier remains available, but it is not treated as ground-truth mine-subsidence prediction. Its training data includes simulator/physics-informed synthetic states.

## Validation

The backend was syntax-checked and the full AI pipeline was executed against the included SQLite dataset. The frontend build could not be executed in this environment because the ZIP does not include `node_modules` and the environment does not have Vite installed.

## Safety positioning

This is a prototype early-warning/risk-screening system. It does not certify mine safety, predict collapse time, or replace qualified mine/geotechnical safety decisions. Field calibration and validation with real mine data are required before operational deployment.

## Runtime fixes added after field testing

### scikit-learn model compatibility
The Isolation Forest artifact is a joblib pickle and must not be loaded across incompatible scikit-learn versions. `backend/ml/isolation_forest.py` now records the training sklearn version in metadata and automatically retrains the local artifact from the bundled SQLite gateway data when the installed sklearn version differs. This prevents repeated `InconsistentVersionWarning` messages and avoids unsafe cross-version unpickling during normal startup/use.

### SQLite connection exhaustion
The React dashboard can issue several AI/API requests concurrently. The SQLite SQLAlchemy engine now uses `NullPool` with a connection timeout, so short-lived requests do not exhaust the default QueuePool. This fixes `QueuePool limit ... connection timed out` errors seen when `/api/ai/latest` and `/api/ai/summary` were called concurrently.

### Validation
`backend/validate_ai.py` now validates the complete hybrid pipeline (Isolation Forest + temporal + spatial + sensor health + risk fusion). The simulator test passes with NORMAL, WARNING and CRITICAL behavior consistent with the project's multi-evidence design. These are simulator checks, not field validation.


## Final live-data responsiveness fixes

- FastAPI `/api/gateway-data` now only validates and commits the incoming packet, then schedules AI inference in a single coalescing background worker.
- AI inference is cached in memory (`MINEWATCH_AI_CACHE_LIMIT`, default 240 rows). `/api/ai/latest`, `/api/ai/history`, `/api/ai/summary`, `/api/alerts`, and GIS reuse the cached result instead of recomputing the full model pipeline on every browser poll.
- New gateway packets trigger a refresh request without blocking the simulator/ESP32 acknowledgement.
- Frontend API configuration is standardized on `http://127.0.0.1:8000`; `frontend/.env` and the legacy/stage9 references were corrected.
- Backend startup explicitly uses port 8000.
- Frontend polling intervals were relaxed for AI/alerts/GIS to reduce unnecessary concurrent SQLite/ML work while retaining live updates.
- Simulator HTTP read timeout is now 10 seconds with a 2-second connection timeout. This is a resilience fallback; normal gateway acknowledgements should return much faster because AI inference is asynchronous.
