import socket
import numpy as np
import os
from multiprocessing import Process, Queue, Manager, Event
from multiprocessing.managers import BaseManager
import paho.mqtt.client as mqtt
import queue
import time
import platform
import subprocess
import netifaces
import json
import threading
from queue import Empty
import signal
import sys
import delegator
import select

# --- Global Variables ---
active_sockets = set()
mqtt_process = None
socket_process = None
manager_server_thread = None
shutdown_event = Event()  # <--- Define shutdown_event inside main


# --- WiFi Mesh Functions ---
def get_serial():
    if platform.system().lower() != "windows":
        with open('/proc/cpuinfo') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.strip().split(":")[1].strip()
    return None


def scan_wifi(prefix):
    result = subprocess.run(['nmcli', '-t', '-f', 'SSID', 'dev', 'wifi'], capture_output=True, text=True)
    ssids = set(filter(None, result.stdout.strip().split('\n')))
    return [ssid for ssid in ssids if ssid.startswith(prefix)]


def extract_serial_from_ssid(ssid, prefix):
    return ssid[len(prefix):]


def elect_leader(remote_serials):
    if remote_serials:
        return max(remote_serials)
    return None


def setup_ap(serial, prefix, interface, password):
    ssid = prefix + serial
    subprocess.run(['nmcli', 'dev', 'wifi', 'hotspot',
                    'ifname', interface,
                    'con-name', ssid,
                    'ssid', ssid,
                    'band', 'bg',
                    'password', password],
                   check=True)


def disconnect_ap(interface):
    subprocess.run(['nmcli', 'dev', 'disconnect', interface], check=True)


def connect_to_leader(leader_serial, prefix, interface, password):
    disconnect_ap(interface)

    time.sleep(2)

    ssid = prefix + leader_serial
    subprocess.run(['nmcli', 'dev', 'wifi', 'connect',
                    ssid, 'ifname', interface,
                    'password', password],
                   check=True)


# --- MQTT and Socket Infrastructure ---
def mqtt_listener(config, client_ip, server_ip, publish_queue, peer_list, shutdown_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    mqtt_client_sockets = []

    def broadcast_message(topic, msg):
        """
        Sends the topic and message across internal sockets to all network libraries
        """
        dead = []

        for s in mqtt_client_sockets:
            try:
                s.sendall(f"{topic}|{msg}".encode())
            except Exception:
                dead.append(s)
        for s in dead:
            mqtt_client_sockets.remove(s)
            try:
                s.close()
            except:
                pass

    def on_message(client, userdata, message):
        msg = message.payload.decode()
        topic = message.topic
        print(f"[MQTT]{topic}|{msg}")
        # Handle MQTT Server Commands
        if topic == "connect":
            name, ip = msg.split(":")
            if name not in peer_list:
                peer_list[name] = ip
                client.publish("connect", f"{config['name']}:{client_ip}")
        elif topic.startswith("status/"):
            name = topic.split("/", 1)[1]
            if msg == "offline" and name in peer_list:
                del peer_list[name]
        else:
            broadcast_message(topic, msg)

    def on_connect(client, userdata, flags, rc):
        print("[MQTT Listener] MQTT Client Connected Succesfully")
        client.subscribe("#")
        client.subscribe("status/#")
        client.publish("connect", f"{config['name']}:{client_ip}")
        client.publish(f"status/{config['name']}", "online", retain=True)

    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.on_message = on_message
    client.on_connect = on_connect
    client.will_set(f"status/{config['name']}", payload="offline", qos=1, retain=True)
    client.connect(server_ip, 1883)
    client.loop_start()

    def mqtt_broadcast_server():
        """
        Accept internal socket connections
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("localhost", 60001))
        server.listen()
        while True:
            conn, addr = server.accept()
            mqtt_client_sockets.append(conn)
            active_sockets.add(conn)

    # Handle subscribing
    threading.Thread(target=mqtt_broadcast_server, daemon=True).start()

    # Handle publishing last
    while not shutdown_event.is_set():
        try:
            topic, message = publish_queue.get_nowait()
            client.publish(topic, message)
        except Empty:
            time.sleep(0.01)

    client.loop_stop()
    client.disconnect()
    print("[MQTT Listener] Exiting...")

def socket_listener(config, client_ip, server_ip, socket_queue, peer_list, shutdown_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def handle_client(conn, addr):
        print(f"[Socket] Connected to {addr}")
        active_sockets.add(conn)
        try:
            while True:
                size_data = conn.recv(4)
                if not size_data:
                    break
                size = int.from_bytes(size_data, 'big')
                data = b''
                while len(data) < size:
                    packet = conn.recv(min(4096, size - len(data)))
                    if not packet:
                        break
                    data += packet

                if data:
                    try:
                        socket_queue.put_nowait((str(addr), data))
                    except queue.Full:
                        try:
                            socket_queue.get_nowait()  # Discard oldest
                        except queue.Empty:
                            pass
                        socket_queue.put_nowait((str(addr), data))

        except Exception as e:
            print(f"[Socket] Error in handle_client: {e}")

        finally:
            conn.close()
            active_sockets.discard(conn)
            print(f"[Socket] Disconnected from {addr}")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", 25000))
    server_socket.listen()
    server_socket.setblocking(False)

    print("[Socket Listener] Started.")

    try:
        while not shutdown_event.is_set():
            readable, _, _ = select.select([server_socket], [], [], 1.0)
            if server_socket in readable:
                conn, addr = server_socket.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

    except Exception as e:
        print(f"[Socket Listener] Error: {e}")

    finally:
        server_socket.close()
        print("[Socket Listener] Exiting...")
    # while True:
    #     conn, addr = server_socket.accept()
    #     threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


# --- Shared Manager Setup ---
class SharedManager(BaseManager): pass


# --- IP SETTINGS ---
def get_server_ip():
    gws = netifaces.gateways()
    if len(gws['default']) == 0:
        return get_my_ip()
    return gws['default'][netifaces.AF_INET][0]


def get_my_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception as e:
        try:
            return netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
        except (KeyError, IndexError):
            return None


# --- CONFIG ---
def get_config():
    with open("config.json", "r") as f:
        config = json.load(f)
    return config


# --- NETWORK STACK ---

def clear_active_sockets():
    print("[Network Stack] Clearing sockets...")
    for s in list(active_sockets):
        if s:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception as e:
                print(f"[Network Stack] Encountered socket error: {e}")
    active_sockets.clear()
    print("[Network Stack] Clearing sockets... Done")


def stop_mqtt_process():
    global mqtt_process
    if mqtt_process and mqtt_process.is_alive():
        print("[Network Stack] Stopping MQTT Process...")
        mqtt_process.terminate()
        mqtt_process.join()
    mqtt_process = None


def stop_socket_process():
    global socket_process
    if socket_process and socket_process.is_alive():
        print("[Network Stack] Stopping Socket Process...")
        socket_process.terminate()
        socket_process.join()
    socket_process = None


def stop_manager_server():
    global manager_server_thread
    manager_server_thread = None


def stop_network_stack():
    clear_active_sockets()
    stop_mqtt_process()
    stop_socket_process()
    stop_manager_server()


def start_mqtt_listener(config, mqtt_pub_queue, peer_list):
    global mqtt_process
    print("[Network Stack] Starting MQTT Listener...")
    mqtt_process = Process(target=mqtt_listener,
                           args=(config, get_my_ip(), get_server_ip(), mqtt_pub_queue, peer_list, shutdown_event))
    mqtt_process.start()


def start_socket_listener(config, socket_queue, peer_list):
    global socket_process
    print("[Network Stack] Starting Socket Listener...")
    socket_process = Process(target=socket_listener,
                             args=(config, get_my_ip(), get_server_ip(), socket_queue, peer_list, shutdown_event))
    socket_process.start()


def start_manager_server():
    global manager_server_thread
    print("[Network Stack] Starting Shared Variables...")

    def run_manager_server():
        m = SharedManager(address=('', 50000), authkey=b'sharedsecret')
        server = m.get_server()
        server.serve_forever()

    manager_server_thread = threading.Thread(target=run_manager_server, daemon=True)
    manager_server_thread.start()


def start_network_stack(config, mqtt_pub_queue, socket_queue, peer_list):
    start_manager_server()
    start_mqtt_listener(config, mqtt_pub_queue, peer_list)
    start_socket_listener(config, socket_queue, peer_list)


def monitor_and_reelect(my_serial, config, shared_objs, start_event):
    while not shutdown_event.is_set():
        try:
            if platform.system().lower() == "windows":
                print(f"[Monitor] Checking connection...(Windows)")
                result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True, text=True)
                ssid_ok = any(config['LEADER_SSID_PREFIX'] in line for line in result.stdout.splitlines() if
                              "SSID" in line and "BSSID" not in line)
                if "connected" not in result.stdout.lower() or not ssid_ok:
                    raise Exception("[Monitor] Disconnected or wrong network")
            else:
                print("[Monitor] Checking connection... (Linux)")
                cmd = "nmcli -t -f active,ssid dev wifi"
                c = delegator.run(cmd)
                active = [line for line in c.out.splitlines() if line.startswith('yes:')]
                print(f"[Monitor] Active connection: {active}")
                if not active or config['LEADER_SSID_PREFIX'] not in active[0]:
                    raise Exception("Disconnected or wrong network")
            # Connected to a pi network!
            print(f"[Monitor] Successful connection to the network")
            print(f"[Monitor] MQTT listener status: {mqtt_process}")
            print(f"[Monitor] Socket Listener status: {socket_process}")
            if not mqtt_process and not socket_process:
                print(f"[Monitor] Network stack offline... Starting stack")
                start_event.set()
        except Exception as e:
            try:
                print(f"[Monitor] Mesh Network Lost: {e}. Restarting...")
                stop_network_stack()
                time.sleep(5)  # Need to let OS take care of things idk

                if config["can_configure_network"]:

                    seen = scan_wifi(config['LEADER_SSID_PREFIX'])
                    remote_serials = [extract_serial_from_ssid(ssid, config['LEADER_SSID_PREFIX']) for ssid in seen]
                    leader_serial = elect_leader(remote_serials)

                    if not leader_serial or leader_serial == my_serial:
                        print(f"[Monitor] No other Pi's Found... Becoming Leader")
                        setup_ap(my_serial, config['LEADER_SSID_PREFIX'], config['LAN_INTERFACE'],
                                 config['WIFI_PASSWORD'])
                        print(f"[Monitor] Successfully became leader")
                    else:
                        print(f"[Monitor] Mesh Leader Found: {leader_serial}")
                        connect_to_leader(leader_serial, config['LEADER_SSID_PREFIX'], config['LAN_INTERFACE'],
                                          config['WIFI_PASSWORD'])
                        print(f"[Monitor] Successfully connected to: {leader_serial}")

                    time.sleep(5)
                    print(f"[Monitor] Starting stack...")
                    start_event.set()
                    #start_network_stack(config, *shared_objs)
                else:
                    print("[Monitor] Please configure network settings... Exiting...")
                    exit()
            except Exception as ex:
                print("[Monitor] Failed trying to configure network:", ex)
        time.sleep(30)


def graceful_exit(signum, frame, config):
    print("[Shutdown] Shutdown signal received. Exiting...")
    shutdown_event.set()
    print("[Shutdown] Shutting down network stack...")
    stop_network_stack()
    if platform.system().lower() != "windows":
        print("[Shutdown] Disconnecting AP...")
        disconnect_ap(config['LAN_INTERFACE'])
    sys.exit(0)


def main():
    config = get_config()
    my_serial = get_serial()
    plat = platform.system().lower()
    print(f"[Startup] Starting ISE network, use Ctrl-C to exit at anytime")
    print(f"[Startup] Device serial: {my_serial}")
    print(f"[Startup] Device platform: {plat}")

    manager = Manager()
    mqtt_pub_queue = manager.Queue()
    socket_queue = manager.Queue(maxsize=3)
    peer_list = manager.dict()
    peer_list[config['name']] = get_my_ip()

    SharedManager.register('get_mqtt_pub_queue', callable=lambda: mqtt_pub_queue)
    SharedManager.register('get_socket_queue', callable=lambda: socket_queue)
    SharedManager.register('get_peer_list', callable=lambda: peer_list, proxytype=type(peer_list))

    shared_objs = (mqtt_pub_queue, socket_queue, peer_list)

    # Setup restart event (for when i want to start network from main)
    start_event = threading.Event()

    # Setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: graceful_exit(s, f, config))
    signal.signal(signal.SIGTERM, lambda s, f: graceful_exit(s, f, config))

    print(f"[Startup] Starting Monitor...")
    threading.Thread(target=monitor_and_reelect, args=(my_serial, config, shared_objs, start_event), daemon=False).start()

    while not shutdown_event.is_set():
        if start_event.is_set():
            start_network_stack(config, *shared_objs)
            start_event.clear()
        time.sleep(1)

    if mqtt_process:
        mqtt_process.join()
    if socket_process:
        socket_process.join()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
