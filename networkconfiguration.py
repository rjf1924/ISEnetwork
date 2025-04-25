import subprocess
import time

LEADER_SSID_PREFIX = "pi-mesh-"
LAN_INTERFACE = "wlan1"
WIFI_PASSWORD = 'ise411meshnet'
def get_serial():
    with open('/proc/cpuinfo') as f:
        for line in f:
            if line.startswith('Serial'):
                return line.strip().split(":")[1].strip()
    return None

def scan_wifi():
    result = subprocess.run(['nmcli', '-t', '-f', 'SSID', 'dev', 'wifi'], capture_output=True, text=True)
    ssids = set(filter(None, result.stdout.strip().split('\n')))
    return [ssid for ssid in ssids if ssid.startswith(LEADER_SSID_PREFIX)]

def extract_serial_from_ssid(ssid):
    return ssid[len(LEADER_SSID_PREFIX):]

def elect_leader(remote_serials):
    all_serials = remote_serials
    if all_serials:
        return max(all_serials)
    else:
        return None

def setup_ap(my_serial):
    ssid = LEADER_SSID_PREFIX + my_serial
    try:
        subprocess.run(['nmcli', 'dev', 'wifi', 'hotspot',
                        'ifname', LAN_INTERFACE,
                        'con-name', ssid,
                        'ssid', ssid,
                        'band', 'bg',
                        'password', WIFI_PASSWORD],
                       check=True)
    except Exception as error:
        print("Failed")
        print(error)
def connect_to_leader(leader_serial):
    ssid = LEADER_SSID_PREFIX + leader_serial
    subprocess.run(['nmcli', 'dev', 'wifi', 'connect',
                    ssid, 'ifname', LAN_INTERFACE,
                    'password', WIFI_PASSWORD],
                   check=True)
def main():
    my_serial = get_serial()
    print(f"My serial: {my_serial}")

    print("Scanning for nearby mesh APs...")
    seen_ssids = scan_wifi()
    remote_serials = [extract_serial_from_ssid(ssid) for ssid in seen_ssids]
    print(f"Remote Serials: {remote_serials}")

    leader_serial = elect_leader(remote_serials)

    if not leader_serial:
        print("No other mesh nodes found. Becoming leader.")
        setup_ap(my_serial)
        print("Successfully became leader...")
    else:
        print(f"Connecting to leader: {leader_serial}")
        connect_to_leader(leader_serial)

if __name__ == "__main__":
    main()
