#!/bin/bash

# Exit script on any error
set -e

# Update system packages
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

echo "Installing dhcp"
sudo apt install dhcpcd5 -y
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

echo "Setting up NAT from wlan1 to wlan0 using nftables..."
# Create nftables configuration
sudo bash -c 'cat > /etc/nftables.conf <<EOF
#!/usr/sbin/nft -f

table inet nat {
    chain prerouting {
        type nat hook prerouting priority 0;
    }

    chain postrouting {
        type nat hook postrouting priority 100;
        oifname "wlan0" masquerade
    }
}

table inet filter {
    chain forward {
        type filter hook forward priority 0;
        iifname "wlan1" oifname "wlan0" accept
        iifname "wlan0" oifname "wlan1" ct state related,established accept
    }
}
EOF'

# Enable and start nftables service
sudo systemctl enable nftables
sudo systemctl start nftables

# Apply nftables rules
echo "Applying nftables rules..."
sudo nft -f /etc/nftables.conf

# Ensure nftables rules persist on reboot
echo "Ensuring nftables rules persist on reboot..."
sudo systemctl enable nftables

# Restart networking services to apply changes
echo "Restarting networking services..."
sudo systemctl restart networking

# Start services
echo "Starting hostapd and dnsmasq..."
sudo systemctl start hostapd
sudo systemctl start dnsmasq

echo "Access Point setup is complete! Consider rebooting..."
