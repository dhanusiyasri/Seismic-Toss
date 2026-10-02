# MineWatch — AI-Powered Mine Subsidence Monitoring & Early Warning System

> **An intelligent, real-time monitoring platform for detecting, analyzing, and predicting underground mine deformation and providing early warnings for potential safety-critical events.**

---

## 📌 Problem Statement

Underground coal mines are vulnerable to **ground deformation, roof movement, subsidence, and sudden structural changes** that can threaten workers, mining infrastructure, and overall operational safety.

Traditional monitoring approaches often depend on periodic inspections, isolated sensor readings, or manual interpretation of measurements. These approaches can make it difficult to continuously understand how the mine environment is changing and to identify developing deformation patterns early.

### The core challenge

A mine monitoring system should be able to:

* Continuously collect structural and environmental sensor data.
* Detect abnormal deformation patterns in real time.
* Distinguish normal variations from potentially dangerous events.
* Analyze the progression of deformation rather than relying only on individual readings.
* Provide early warnings before a critical situation develops.
* Present complex sensor information through an intuitive dashboard.
* Continue functioning with low-latency local processing where possible.

### Our objective

**MineWatch** aims to provide an integrated hardware-software platform that combines sensor data acquisition, real-time processing, AI-assisted analysis, visualization, and early-warning mechanisms into a single monitoring system.

---

# 💡 Proposed Solution

MineWatch follows a **continuous sensing → analysis → prediction → warning** architecture.

```text
Mine Environment
       ↓
Sensors / Edge Devices
       ↓
Data Acquisition Gateway
       ↓
Real-Time Backend
       ↓
Data Storage
       ↓
AI / Anomaly Detection
       ↓
Risk Assessment
       ↓
Early Warning
       ↓
Monitoring Dashboard
```

The platform is designed to transform raw sensor measurements into actionable information for mine operators and safety personnel.

Instead of simply displaying sensor values, MineWatch attempts to answer:

> **"Is the mine behaving normally, is deformation developing, and does the current pattern require attention?"**

---

# 🏗️ System Architecture

```text
                    ┌───────────────────────┐
                    │   MINE ENVIRONMENT    │
                    │                       │
                    │ Ground / Roof /       │
                    │ Structural Movement   │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │   SENSOR / EDGE NODE  │
                    │                       │
                    │ ESP32 / Sensors       │
                    └───────────┬───────────┘
                                │
                                │ Sensor packets
                                ▼
                    ┌───────────────────────┐
                    │   DATA GATEWAY        │
                    │                       │
                    │ FastAPI Backend       │
                    └───────────┬───────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐
          │     SQLite       │    │  AI Processing   │
          │  Sensor Storage  │    │  & Risk Analysis │
          └────────┬─────────┘    └────────┬─────────┘
                   │                       │
                   └───────────┬───────────┘
                               ▼
                    ┌───────────────────────┐
                    │    MINEWATCH          │
                    │    DASHBOARD          │
                    │                       │
                    │ Live Data             │
                    │ Trends                │
                    │ Alerts                │
                    │ Risk Status           │
                    └───────────────────────┘
```

---

# 🔧 Current Implementation

The current prototype implements the core end-to-end monitoring pipeline.

## 1. Real-Time Sensor Data Pipeline

MineWatch supports a live-data architecture where sensor/ESP32-style data can be sent to the backend through an API endpoint.

```text
Sensor / ESP32
      ↓
POST /api/gateway-data
      ↓
FastAPI Backend
      ↓
SQLite
      ↓
AI Processing
      ↓
React Dashboard
```

The gateway is designed to acknowledge incoming sensor packets quickly rather than blocking the sensor connection while the complete AI pipeline executes.

This allows the monitoring system to continue receiving data while analysis happens in the background.

---

## 2. Sensor Data Simulator

Because physical mine-scale sensor deployment is difficult to reproduce during development and a hackathon demonstration, MineWatch includes a configurable sensor simulator.

The simulator can reproduce different mine conditions.

### Available scenarios

#### NORMAL

Represents stable operating conditions with normal sensor variations.

```text
Normal sensor behaviour
        ↓
Low risk
        ↓
Normal system status
```

#### GRADUAL_DEFORMATION

Simulates progressively increasing deformation.

```text
Small deformation
       ↓
Increasing deformation
       ↓
Trend detected
       ↓
Increasing risk
```

#### SUDDEN_MOVEMENT

Simulates an abrupt structural movement event.

```text
Normal state
       ↓
Sudden sensor change
       ↓
Anomaly detected
       ↓
Warning
```

#### SEVERE_EVENT

Simulates a high-severity abnormal event requiring immediate attention.

```text
Critical sensor behaviour
       ↓
Severe anomaly
       ↓
High-risk condition
       ↓
Emergency warning
```

---

# 🧠 AI-Assisted Monitoring

MineWatch is designed to move beyond simple threshold-based monitoring.

Instead of asking only:

> "Did the sensor cross a fixed limit?"

the system can analyze:

* Current sensor values
* Historical measurements
* Rate of change
* Deformation trends
* Sudden deviations
* Multiple sensor signals
* Temporal patterns

This enables the system to identify abnormal behaviour and estimate the severity of the current condition.

---

# 📊 Monitoring Dashboard

The React-based dashboard provides a centralized interface for monitoring the mine environment.

The dashboard is designed to expose:

* Live sensor information
* Sensor trends
* Current system state
* Detected anomalies
* Risk indicators
* Warning conditions
* Historical behaviour

The objective is to allow operators to understand the current condition of the mine without manually interpreting large amounts of raw sensor data.

---

# 🚨 Early Warning Concept

MineWatch uses the progression of sensor behaviour to classify the current condition.

A conceptual risk pipeline is:

```text
Sensor Data
     ↓
Data Validation
     ↓
Feature Extraction
     ↓
Anomaly Detection
     ↓
Trend Analysis
     ↓
Risk Assessment
     ↓
Warning Level
```

Possible operational states include:

```text
🟢 NORMAL
   ↓
🟡 MONITOR
   ↓
🟠 WARNING
   ↓
🔴 CRITICAL
```

The exact thresholds and risk models can be calibrated using real mine sensor data during future deployment.

---

# 🖥️ Technology Stack

## Frontend

* React
* Vite
* JavaScript / TypeScript ecosystem
* Web-based dashboard

## Backend

* Python
* FastAPI
* REST APIs
* Background processing

## Database

* SQLite for the current prototype

SQLite provides a lightweight local database suitable for development and demonstration.

For production deployment, this can be migrated to a more scalable database such as PostgreSQL or a time-series database.

## Edge / Hardware

* ESP32-compatible architecture
* Sensor nodes
* Gateway communication

The current prototype supports simulated sensor packets so that the complete monitoring architecture can be demonstrated without requiring a physical mine.

## AI / Analytics

The architecture supports:

* Sensor anomaly detection
* Time-series analysis
* Deformation trend analysis
* Risk classification
* Future predictive modelling

---

# 📂 Repository Structure

```text
Seismic-Toss/
│
├── backend/
│   └── Backend and API services
│
├── frontend/
│   └── React/Vite monitoring dashboard
│
├── simulator/
│   └── Sensor and mine-condition simulator
│
├── IMPLEMENTATION_NOTES.md
│   └── Development and implementation notes
│
├── POLISH_REPORT.md
│   └── Prototype refinement notes
│
├── START_MINEWATCH.bat
│   └── Starts the backend
│
├── START_FRONTEND.bat
│   └── Starts the frontend
│
├── START_SIMULATOR.bat
│   └── Starts the sensor simulator
│
└── README.md
```

---

# 🚀 Getting Started

## Prerequisites

Install the following before running MineWatch:

* Python 3.9+
* Node.js
* npm
* Git

Verify the installations:

```bash
python --version
node --version
npm --version
git --version
```

---

# 📥 Installation

Clone the repository:

```bash
git clone https://github.com/dhanusiyasri/Seismic-Toss.git
```

Move into the project directory:

```bash
cd Seismic-Toss
```

---

# ▶️ Running the Project

MineWatch consists of three components:

1. Backend
2. Frontend
3. Sensor simulator

Run them in **three separate terminals**.

---

## Terminal 1 — Start Backend

On Windows:

```text
START_MINEWATCH.bat
```

The backend will run at:

```text
http://127.0.0.1:8000
```

FastAPI Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

The Swagger interface can be used to inspect and test the available API endpoints.

---

## Terminal 2 — Start Frontend

Run:

```text
START_FRONTEND.bat
```

The Vite development server will normally be available at:

```text
http://localhost:5173
```

Open the displayed URL in your browser.

The frontend is configured to communicate with the backend through:

```text
http://127.0.0.1:8000
```

---

## Terminal 3 — Start Sensor Simulator

Run:

```text
START_SIMULATOR.bat
```

The default simulation scenario is:

```text
NORMAL
```

The simulator sends sensor packets to the backend, allowing the complete MineWatch pipeline to be demonstrated without physical sensors.

---

# 🧪 Running Different Simulation Scenarios

The simulator can be used to demonstrate different mine conditions.

### Normal condition

```bash
python sensor_simulator.py --scenario NORMAL
```

### Gradual deformation

```bash
python sensor_simulator.py --scenario GRADUAL_DEFORMATION
```

### Sudden movement

```bash
python sensor_simulator.py --scenario SUDDEN_MOVEMENT
```

### Severe event

```bash
python sensor_simulator.py --scenario SEVERE_EVENT
```

These scenarios allow the dashboard and AI analysis pipeline to be tested under different simulated conditions.

---

# 🔄 Live Data Flow

Once all three components are running:

```text
             SENSOR SIMULATOR
                    │
                    │ Sensor packets
                    ▼
          ┌────────────────────┐
          │   FastAPI Gateway  │
          │                    │
          │ /api/gateway-data  │
          └─────────┬──────────┘
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
      ┌────────┐       ┌────────────────┐
      │ SQLite │       │ Background AI  │
      └────┬───┘       └───────┬────────┘
           │                   │
           └─────────┬─────────┘
                     ▼
             ┌───────────────┐
             │ React         │
             │ Dashboard     │
             └───────────────┘
```

The gateway is intentionally designed to acknowledge incoming sensor packets quickly while AI processing occurs asynchronously. This prevents sensor/simulator requests from timing out while the dashboard continues to request analysis results.

---

# 🔮 Planned Improvements

The current repository represents a working prototype. The following capabilities are planned for future versions.

## 1. Real Hardware Sensor Integration

Replace the simulator with physical sensor nodes.

Potential sensors include:

* Accelerometers
* Tilt/inclinometer sensors
* Displacement sensors
* Strain sensors
* Vibration sensors
* Environmental sensors

The goal is to establish:

```text
Physical Mine
     ↓
Sensor Node
     ↓
ESP32 / Edge Gateway
     ↓
MineWatch Backend
```

---

## 2. Multi-Sensor Fusion

Future versions will combine measurements from multiple sensors instead of evaluating each sensor independently.

```text
Sensor 1 ─┐
Sensor 2 ─┤
Sensor 3 ─┼──→ Sensor Fusion → Risk Assessment
Sensor 4 ─┤
Sensor 5 ─┘
```

This can provide a more comprehensive representation of ground behaviour.

---

## 3. Predictive Deformation Modelling

Future versions will investigate time-series machine-learning models capable of predicting deformation trends.

Potential approaches include:

* Random Forest
* XGBoost
* LSTM
* Temporal CNN
* Transformer-based time-series models

The final model should be selected based on real mine data, validation performance, latency, and deployment constraints.

---

## 4. Real-Time Alert System

Future deployments can provide alerts through:

* Dashboard notifications
* SMS
* Mobile notifications
* Email
* Local sirens
* Control-room alerts

The objective is to ensure that critical information reaches responsible personnel quickly.

---

## 5. Edge AI

AI inference can progressively be moved closer to the sensor layer.

```text
Cloud / Server AI
        ↓
Gateway AI
        ↓
Edge AI
        ↓
Sensor Node
```

This can reduce:

* Network dependency
* Communication latency
* Bandwidth requirements

and improve resilience in underground environments.

---

## 6. Offline-First Operation

Underground mines can have unreliable connectivity.

Future versions will support:

* Local data buffering
* Store-and-forward communication
* Local AI inference
* Automatic synchronization when connectivity returns

---

## 7. Production-Grade Database

The current prototype uses SQLite.

Future deployments can use:

* PostgreSQL
* TimescaleDB
* Distributed storage
* Dedicated archival storage

depending on deployment scale and sensor frequency.

---

## 8. Mine Digital Twin

A future version can visualize sensor locations on a digital representation of the mine.

```text
             MINE DIGITAL TWIN

       Sensor A ●────────────● Sensor B
                 │            │
                 │            │
       Sensor C ●────────────● Sensor D
                 │
                 ● Sensor E

                     ↓

             Real-Time Risk Map
```

This would allow operators to identify **where** abnormal behaviour is occurring rather than only seeing numerical sensor values.

---

# 🎯 Expected Impact

MineWatch is intended to support a transition from:

```text
Periodic Inspection
       ↓
Manual Interpretation
       ↓
Reactive Response
```

towards:

```text
Continuous Monitoring
       ↓
AI-Assisted Analysis
       ↓
Early Detection
       ↓
Proactive Safety Response
```

The platform can ultimately help mining organizations improve situational awareness, reduce dependence on manual monitoring, and identify potentially dangerous deformation patterns earlier.

---

# ⚠️ Prototype Disclaimer

MineWatch is currently a **research and demonstration prototype**.

The current implementation uses simulated/physics-informed sensor scenarios for demonstrating the complete monitoring architecture. It has **not been field-validated and must not be treated as a certified mine-safety or emergency-warning system**.

Real-world deployment would require:

* Field calibration
* Validated sensor hardware
* Real mine datasets
* Extensive model validation
* Failure-mode analysis
* Redundant sensing
* Communication reliability testing
* Safety certification
* Approval by the relevant mining authorities

---

# 🤝 Future Vision

The long-term vision of MineWatch is to evolve from a prototype monitoring dashboard into a **complete intelligent mine-safety platform** that combines:

**IoT sensing + Edge Computing + AI/ML + Real-Time Analytics + Predictive Monitoring + Early Warning + Digital Mine Visualization**

into one integrated system.

---

# 🏁 Conclusion

**MineWatch transforms raw underground mine sensor data into meaningful safety intelligence.**

By combining continuous sensing, real-time data processing, AI-assisted anomaly detection, predictive analytics, and an intuitive monitoring dashboard, the platform aims to move mine safety from **reactive observation toward proactive, data-driven monitoring**.

> **MineWatch — Sense the ground. Understand the change. Warn before it becomes critical.**

---

## 📜 Project Status

**Current Status:** Working Prototype

**Current Mode:** Sensor Simulation + Real-Time Dashboard + AI-Assisted Monitoring

**Future Mode:** Physical Sensor Network + Edge AI + Predictive Mine Digital Twin

---

## 👥 Contributors

Developed as a Smart India Hackathon project.

**Repository:**
https://github.com/dhanusiyasri/Seismic-Toss

---

## ⭐ If You Find This Project Useful

Consider giving the repository a ⭐ and following the project as MineWatch evolves from a prototype into a real-world intelligent mine monitoring platform.
