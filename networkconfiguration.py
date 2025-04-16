import subprocess
import time

LEADER_SSID_PREFIX = "pi-mesh-"
WIFI_INTERFACE = "wlan0"

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

def elect_leader(remote_serials, my_serial):
    all_serials = remote_serials + [my_serial]
    return max(all_serials)

def setup_ap(my_serial):
    ssid = LEADER_SSID_PREFIX + my_serial
    subprocess.run(['nmcli', 'dev', 'wifi', 'hotspot', 'ifname', WIFI_INTERFACE,
                    'con-name', ssid, 'ssid', ssid, 'band', 'bg', 'password', 'meshpassword'],
                   check=True)

def connect_to_leader(leader_serial):
    ssid = LEADER_SSID_PREFIX + leader_serial
    subprocess.run(['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', 'meshpassword'],
                   check=True)

def main():
    my_serial = get_serial()
    print(f"My serial: {my_serial}")

    # print("Scanning for nearby mesh APs...")
    # seen_ssids = scan_wifi()
    # remote_serials = [extract_serial_from_ssid(ssid) for ssid in seen_ssids]
    #
    # if not remote_serials:
    #     print("No other mesh nodes found. Becoming leader.")
    #     setup_ap(my_serial)
    #     return
    #
    # leader_serial = elect_leader(remote_serials, my_serial)
    #
    # if leader_serial == my_serial:
    #     print("I am the leader.")
    #     setup_ap(my_serial)
    # else:
    #     print(f"Connecting to leader: {leader_serial}")
    #     connect_to_leader(leader_serial)

if __name__ == "__main__":

    main()
