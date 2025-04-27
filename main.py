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
import random
import select
from config_helper import get_config

# --- Global Variables ---
active_sockets = set()
mqtt_process = None
socket_process = None
manager_server_thread = None
shutdown_total_event = Event()
shutdown_mqtt_event = Event()
shutdown_socket_event = Event()


# --- WiFi Election Functions ---
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


def should_become_leader(my_serial, seen_serials):
    if not seen_serials:
        return True
    max_seen = max(seen_serials)
    return my_serial >= max_seen


def elect_leader(remote_serials):
    if remote_serials:
        return max(remote_serials)
    return None


def handle_leader_election(my_serial, config):
    prefix = config['LEADER_SSID_PREFIX']
    interface = config['LAN_INTERFACE']
    password = config['WIFI_PASSWORD']

    seen_serials = scan_for_leaders(prefix)

    if seen_serials:
        leader_serial = elect_leader(seen_serials)
        if leader_serial:
            print(f"[Election] Found leader {leader_serial} immediately. Connecting...")
            connect_to_leader(leader_serial, prefix, interface, password)
            return

    wait_time = random.uniform(1, 30)
    print(f"[Election] No leader found. Waiting {wait_time:.1f}s before self-promotion...")
    start = time.time()

    while time.time() - start < wait_time:
        if shutdown_total_event.is_set():
            return

        seen_serials = scan_for_leaders(prefix)
        if seen_serials:
            leader_serial = elect_leader(seen_serials)
            if leader_serial:
                print(f"[Election] Found leader {leader_serial} during backoff. Connecting...")
                connect_to_leader(leader_serial, prefix, interface, password)
                return

        time.sleep(0.5)

    print(f"[Election] No leader appeared. Promoting self to leader...")
    setup_ap(my_serial, prefix, interface, password)


def scan_for_leaders(prefix):
    seen = scan_wifi(prefix)
    return [extract_serial_from_ssid(ssid, prefix) for ssid in seen]


def get_ssid(interface):
    system = platform.system().lower()
    try:
        if system == "windows":
            result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":", 1)[1].strip()
                    if ssid:
                        return ssid
        else:
            result = subprocess.run(
                ['nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', interface],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip() or None
    except Exception as e:
        print(f"[Get SSID] Error: {e}")
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


def disconnect_ap(interface, leader_prefix):
    try:
        ssid = get_ssid(interface)
        if ssid and leader_prefix in ssid:
            subprocess.run(['nmcli', 'connection', 'delete', ssid], check=True)
    except Exception as e:
        pass

    try:
        subprocess.run(['nmcli', 'device', 'disconnect', interface], check=True)
        time.sleep(5)
        subprocess.run(['nmcli', 'device', 'connect', interface], check=True)
    except Exception as e:
        print(f"[Disconnect AP] Error during device reset: {e}")


def connect_to_leader(leader_serial, prefix, interface, password):
    ssid = prefix + leader_serial
    try:
        subprocess.run(['nmcli', 'dev', 'wifi', 'connect',
                        ssid, 'ifname', interface,
                        'password', password],
                       check=True)
    except Exception as e:
        print("[Connect AP] Failed to connect to leader...")


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
        print(f"[MQTT]{topic:<50}|{msg}")
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
    client.connect(server_ip, int(config["mosquitto_port"]))
    client.loop_start()

    def mqtt_broadcast_server():
        """
        Accept internal socket connections for subscribers
        """
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("localhost", 60001))
        server.listen()
        server.settimeout(1.0)

        try:
            while not shutdown_event.is_set():
                try:
                    conn, addr = server.accept()
                    mqtt_client_sockets.append(conn)
                    active_sockets.add(conn)
                except socket.timeout:
                    continue  # just loop again if no connection
                except Exception as e:
                    print(f"[Broadcast Server] Error: {e}")
        finally:
            server.close()
            print("[Broadcast Server] Exiting...")

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
        try:
            active_sockets.add(conn)
            recv_buffer = bytearray()

            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                recv_buffer.extend(chunk)

                while len(recv_buffer) >= 4:
                    size = int.from_bytes(recv_buffer[:4], 'big')
                    if len(recv_buffer) < 4 + size:
                        break
                    data = recv_buffer[4:4 + size]
                    try:
                        socket_queue.put_nowait((str(addr), data))
                    except queue.Full:
                        try:
                            socket_queue.get_nowait()
                        except queue.Empty:
                            pass
                        socket_queue.put_nowait((str(addr), data))
                    recv_buffer = recv_buffer[4 + size:]

        except Exception as e:
            print(f"[Socket] Error: {e}")
        finally:
            active_sockets.discard(conn)
            conn.close()
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
    shutdown_mqtt_event.set()
    if mqtt_process and mqtt_process.is_alive():
        print("[Network Stack] Stopping MQTT Process...")
        # mqtt_process.terminate(timeout=10)
        mqtt_process.join(timeout=10)
        if mqtt_process and mqtt_process.is_alive():
            print("[Network Stack] Forcing MQTT Process to stop...")
            mqtt_process.terminate()
            mqtt_process.join()
    shutdown_mqtt_event.clear()
    mqtt_process = None


def stop_socket_process():
    global socket_process
    shutdown_socket_event.set()
    if socket_process and socket_process.is_alive():
        print("[Network Stack] Stopping Socket Process...")
        # socket_process.terminate()
        socket_process.join(timeout=10)
        if socket_process and socket_process.is_alive():
            print("[Network Stack] Forcing Socket Process to stop...")
            socket_process.terminate()
            socket_process.join()
    shutdown_socket_event.clear()
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
                           args=(config, get_my_ip(), get_server_ip(), mqtt_pub_queue, peer_list, shutdown_mqtt_event))
    mqtt_process.start()


def start_socket_listener(config, socket_queue, peer_list):
    global socket_process
    print("[Network Stack] Starting Socket Listener...")
    socket_process = Process(target=socket_listener,
                             args=(
                                 config, get_my_ip(), get_server_ip(), socket_queue, peer_list, shutdown_socket_event))
    socket_process.start()


def start_manager_server():
    global manager_server_thread
    print("[Network Stack] Starting Shared Variables...")

    def run_manager_server():
        try:
            m = SharedManager(address=('', 50000), authkey=b'sharedsecret')
            server = m.get_server()
            server.serve_forever()
        except:
            pass

    if manager_server_thread and not manager_server_thread.is_alive() or not manager_server_thread:
        manager_server_thread = threading.Thread(target=run_manager_server, daemon=True)
        manager_server_thread.start()


def start_network_stack(config, mqtt_pub_queue, socket_queue, peer_list):
    start_manager_server()
    start_mqtt_listener(config, mqtt_pub_queue, peer_list)
    start_socket_listener(config, socket_queue, peer_list)


def print_peer_list(peer_list: dict):
    for name, ip in peer_list.items():
        print(f"{name:<15}|{ip}")


class NetworkMonitor:
    def __init__(self, config, shared_objs, start_event):
        self.config = config
        self.shared_objs = shared_objs
        self.start_event = start_event
        self.shutdown_event = shutdown_total_event
        self.my_serial = get_serial()

    def run(self):
        while not self.shutdown_event.is_set():
            try:
                self.check_connection()
            except Exception as e:
                try:
                    print(f"[Monitor] Mesh Network Lost: {e}. Restarting...")
                    self.reconnect()
                except Exception as e:
                    print(f"[Monitor] Failed trying to configure network: {e}")
            self.wait_interruptible(30)

    def check_connection(self):
        print(f"[Monitor] Checking connection...")
        ssid = get_ssid(self.config['LAN_INTERFACE'])
        print(f"[Monitor] Connection: {ssid}")
        print(f"[Monitor] Peers: ")
        print_peer_list(self.shared_objs[2])

        if not ssid or self.config['LEADER_SSID_PREFIX'] not in ssid:
            raise Exception("Disconnected or wrong network")

        print(f"[Monitor] MQTT listener status: {mqtt_process}")
        print(f"[Monitor] Socket Listener status: {socket_process}")

        if not mqtt_process and not socket_process:
            print(f"[Monitor] Network stack offline... Starting stack")
            self.start_event.set()
        # Healing of processes
        if mqtt_process and not mqtt_process.is_alive():
            print(f"[Monitor] MQTT Process offline... Attempting restart")
            stop_mqtt_process()
            start_mqtt_listener(self.config, self.shared_objs[0], self.shared_objs[2])
        if socket and not socket_process.is_alive():
            print(f"[Monitor] Socket Process offline... Attempting restart")
            stop_socket_process()
            start_socket_listener(self.config, self.shared_objs[1], self.shared_objs[2])

    def reconnect(self):
        print(f"[Monitor] Restarting...")
        stop_network_stack()
        self.wait_interruptible(5)
        if not self.config["can_configure_network"]:
            print("[Monitor] Please configure network settings... Exiting...")
            sys.exit(1)

        handle_leader_election(self.my_serial, self.config)

        # seen = scan_wifi(self.config['LEADER_SSID_PREFIX'])
        # leader_serial = elect_leader([extract_serial_from_ssid(s, self.config['LEADER_SSID_PREFIX']) for s in seen])
        #
        # if not leader_serial or leader_serial == self.my_serial:
        #     print(f"[Monitor] No other Pi's Found... Becoming Leader")
        #     setup_ap(self.my_serial, self.config['LEADER_SSID_PREFIX'], self.config['LAN_INTERFACE'],
        #              self.config['WIFI_PASSWORD'])
        #     print(f"[Monitor] Successfully became leader")
        # else:
        #     print(f"[Monitor] Mesh Leader Found: {leader_serial}")
        #     connect_to_leader(leader_serial, self.config['LEADER_SSID_PREFIX'], self.config['LAN_INTERFACE'],
        #                       self.config['WIFI_PASSWORD'])
        #     print(f"[Monitor] Successfully connected to: {leader_serial}")

        # Update My Peer list value
        self.shared_objs[2][self.config['name']] = get_my_ip()
        self.wait_interruptible(5)
        print(f"[Monitor] Starting stack...")
        self.start_event.set()

    def wait_interruptible(self, seconds):
        for _ in range(seconds):
            if self.shutdown_event.wait(1):
                break


def graceful_exit(signum, frame, config):
    print("[Shutdown] Shutdown signal received. Exiting...")
    shutdown_total_event.set()
    print("[Shutdown] Shutting down network stack...")
    stop_network_stack()
    if platform.system().lower() != "windows":
        print("[Shutdown] Disconnecting AP...")
        disconnect_ap(config['LAN_INTERFACE'], config['LEADER_SSID_PREFIX'])
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
    socket_queue = manager.Queue(maxsize=10)
    peer_list = manager.dict()
    peer_list[config['name']] = "0.0.0.0"

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
    monitor = NetworkMonitor(config, shared_objs, start_event)
    threading.Thread(target=monitor.run, daemon=False).start()
    # threading.Thread(target=monitor_and_reelect, args=(my_serial, config, shared_objs, start_event),
    #                  daemon=False).start()

    while not shutdown_total_event.is_set():
        if start_event.is_set():
            # Required to be in main by windows
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
