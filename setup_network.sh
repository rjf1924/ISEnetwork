#!/bin/bash

# Exit script on any error
set -e

# Update system packages
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

# Install required packages
echo "Installing hostapd and dnsmasq..."
sudo apt install -y hostapd dnsmasq

# Enable services
echo "Enabling services..."
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq

# Configure static IP for wlan0
echo "Configuring static IP for wlan1..."
sudo bash -c 'cat >> /etc/dhcpcd.conf <<EOF

interface wlan1
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF'

sudo systemctl restart dhcpcd

# Backup default dnsmasq configuration
echo "Backing up dnsmasq configuration..."
sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig

# Configure dnsmasq for DHCP
echo "Configuring dnsmasq..."
sudo bash -c 'cat > /etc/dnsmasq.conf <<EOF
interface=wlan1
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,9999d
EOF'

# Configure hostapd for Access Point
echo "Configuring hostapd..."
sudo bash -c 'cat > /etc/hostapd/hostapd.conf <<EOF
interface=wlan1
driver=nl80211
ssid=ICEnetwork
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=ise2025
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF'

# Point hostapd to the configuration file
echo "Linking hostapd configuration..."
sudo bash -c 'echo DAEMON_CONF=\"/etc/hostapd/hostapd.conf\" > /etc/default/hostapd'

# Enable IP forwarding for internet sharing
echo "Enabling IP forwarding..."
sudo sed -i "s/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/" /etc/sysctl.conf
sudo sysctl -p

# Setup NAT (Network Address Translation) from wlan1 to wlan0
echo "Setting up NAT from wlan1 to wlan0..."
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -i wlan1 -o wlan0 -j ACCEPT
sudo iptables -A FORWARD -i wlan0 -o wlan1 -m state --state RELATED,ESTABLISHED -j ACCEPT

# Save iptables rules
sudo sh -c "iptables-save > /etc/iptables.ipv4.nat"

# Make iptables persistent on reboot
echo "Making NAT persistent..."
grep -qxF 'iptables-restore < /etc/iptables.ipv4.nat' /etc/rc.local || sudo bash -c 'sed -i "/^exit 0/i iptables-restore < /etc/iptables.ipv4.nat" /etc/rc.local'

# Restart networking services to apply changes
echo "Restarting networking services..."
sudo systemctl restart networking

# Start services
echo "Starting hostapd and dnsmasq..."
sudo systemctl start hostapd
sudo systemctl start dnsmasq

echo "Access Point setup is complete! Consider rebooting..."
