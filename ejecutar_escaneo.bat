@echo off
cd /d C:\vintedbot
python escanear.py >> data\log_escaneos.txt 2>&1
