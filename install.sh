#!/bin/bash

# Exit immediately if any command fails
set -e

# Define virtual environment directory name
VENV_DIR="venv"
# Define script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Update and upgrade system packages (optional)
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install mosquito clients
echo "Installing mosquito and mosquito-clients"
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv $VENV_DIR

# Activate virtual environment
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# Upgrade pip inside the virtual environment
echo "Upgrading pip..."
pip install --upgrade pip

# Install required packages from requirements.txt
if [ -f "requirements.txt" ]; then
    echo "Installing packages from requirements.txt..."
    pip install -r requirements.txt
else
    echo "No requirements.txt file found!"
fi

# Prompt for name
read -p "Enter a device name: " devicename

# Save to config.json
echo "Saving configuration..."
cat > "$SCRIPT_DIR/config.json" <<EOF
{
  "name": "${devicename}",
  "LEADER_SSID_PREFIX": "pi-mesh-",
  "LAN_INTERFACE": "wlan0",
  "WIFI_PASSWORD": "ise411meshnet",
  "can_configure_network": true
}
EOF

echo "Setup complete. To activate the environment later, run:"
echo "source $VENV_DIR/bin/activate"