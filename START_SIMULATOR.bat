@echo off
setlocal
cd /d "%~dp0simulator"
echo Starting MineWatch sensor simulator...
python sensor_simulator.py
