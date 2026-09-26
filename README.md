# MineWatch

## Quick Start (Final SIH Prototype)

1. Start the backend:
   - Run `START_MINEWATCH.bat`
   - Backend: `http://127.0.0.1:8000`
   - Swagger: `http://127.0.0.1:8000/docs`

2. Start the frontend in a second terminal:
   - Run `START_FRONTEND.bat`
   - Open the Vite URL shown in the terminal (normally `http://localhost:5173`).

3. Start the simulator in a third terminal:
   - Run `START_SIMULATOR.bat`
   - Default scenario is `NORMAL`, 0.5 seconds per packet.

### Live-data architecture

`Simulator/ESP32 -> POST /api/gateway-data -> SQLite -> background AI cache -> React dashboard`

The gateway endpoint intentionally does **not** run the full ML pipeline synchronously. It acknowledges sensor packets immediately and refreshes the AI result in a coalescing background worker. This prevents the simulator from timing out while the dashboard polls AI endpoints.

The frontend is standardized on backend port **8000** through `frontend/.env` (`VITE_API_URL=http://127.0.0.1:8000`).

For a stronger demonstration, run:
- `python sensor_simulator.py --scenario NORMAL`
- `python sensor_simulator.py --scenario GRADUAL_DEFORMATION`
- `python sensor_simulator.py --scenario SUDDEN_MOVEMENT`
- `python sensor_simulator.py --scenario SEVERE_EVENT`

This remains a prototype using simulator/physics-informed evidence and is not field-validated safety certification.
