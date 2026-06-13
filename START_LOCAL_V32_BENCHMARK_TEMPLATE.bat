@echo off
chcp 65001 > nul
echo Use RunPod JSON: {"input":{"task":"benchmark_template"}}
python handler.py
pause
