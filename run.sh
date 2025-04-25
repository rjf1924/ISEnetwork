#!/bin/bash

# Exit immediately if any command fails
set -e
source venv/bin/activate

# Start mosquitto
sudo systemctl start mosquitto

# Run the Python script
python3 main.py

# Deactivate the virtual environment after execution
deactivate