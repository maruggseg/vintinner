@echo off
cd /d C:\vintedbot
python alertas.py >> data\log_alertas.txt 2>&1
