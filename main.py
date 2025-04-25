# import socket
# import numpy as np
# from multiprocessing import Process, Queue, Manager
# from multiprocessing.managers import BaseManager
# import paho.mqtt.client as mqtt
# import time
# import subprocess
# import netifaces
# import json
# import threading
# from queue import Empty
# import signal
# import sys
#
# active_sockets = set()
#
#
# def mqtt_listener(config, client_ip, server_ip, publish_queue: Queue, peer_list, last_heartbeat, mqtt_callbacks):
#     print(f"mqtt_listener started...")
#     mqtt_client_sockets = []
#
#     def broadcast_message(topic, msg):
#         dead = []
#         for s in mqtt_client_sockets:
#             try:
#                 s.sendall(f"{topic}|{msg}".encode())
#             except Exception:
#                 dead.append(s)
#
#         # Remove any dead sockets
#         for s in dead:
#             mqtt_client_sockets.remove(s)
#             try:
#                 s.close()
#             except:
#                 pass
#
#     def on_message(client, userdata, message):
#         # print(f"Client: {client}")
#         # print(f"Userdata: {userdata}")
#         msg = message.payload.decode()
#         topic = message.topic
#         print(f"MQTT: {topic}:{msg}")
#
#         # Handle connect event
#         if topic == "connect":
#             name, ip = msg.split(":")
#             if name not in peer_list:
#                 print(f"Registered {name} under {ip}")
#                 peer_list[name] = ip
#                 client.publish("connect", f"{config['name']}:{client_ip}")
#
#         # Handle status events
#         elif topic.startswith("status/"):
#             name = topic.split("/", 1)[1]
#             if msg == "offline":
#                 if name in peer_list:
#                     print(f"{name} went offline, removing from peer_list")
#                     del peer_list[name]
#         else:
#             broadcast_message(topic, msg)
#
#     def on_connect(client, userdata, flags, rc):
#         print(f"MQTT Connected with result code {rc}")
#         client.subscribe("#")
#         client.subscribe("status/#")
#         client.subscribe("heartbeat/#")
#         client.publish("connect", f"{config['name']}:{client_ip}")
#         client.publish(f"status/{config['name']}", "online", retain=True)
#
#     try:
#         client = mqtt.Client()
#         client.on_message = on_message
#         client.on_connect = on_connect
#         client.will_set(f"status/{config['name']}", payload="offline", qos=1, retain=True)
#         client.connect(server_ip, 1883)
#
#         client.loop_start()
#
#         def mqtt_broadcast_server():
#             server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             server.bind(("localhost", 60001))
#             server.listen()
#
#             print("[MQTT Broadcast Server] Listening on port 60001")
#             while True:
#                 conn, addr = server.accept()
#                 print(f"[MQTT subscriber connected] {addr}")
#                 mqtt_client_sockets.append(conn)
#                 active_sockets.add(conn)
#
#         threading.Thread(target=mqtt_broadcast_server, daemon=True).start()
#
#         # Handle publish queue
#         while True:
#             try:
#                 msg = publish_queue.get_nowait()
#                 topic, message = msg
#                 client.publish(topic, message)
#             except Empty:
#                 continue
#
#     except Exception as e:
#         print(f"[Error connecting MQTT Listener]")
#         print(e)
#
#
# # Socket Setup
# def socket_listener(config, client_ip, server_ip, socket_queue):
#     print("Socket listener started...")
#
#     def handle_client(conn, addr):
#         print(f"[+] Connected: {addr}")
#         active_sockets.add(conn)
#         try:
#             while True:
#                 size_data = conn.recv(4)
#                 if not size_data:
#                     break
#                 size = int.from_bytes(size_data, 'big')
#
#                 data = b''
#                 while len(data) < size:
#                     packet = conn.recv(min(4096, size - len(data)))
#                     if not packet:
#                         break
#                     data += packet
#
#                 if data:
#                     socket_queue.put((str(addr), data))
#                     print(f"[{addr}] {size}")
#         except Exception as e:
#             print(f"[!] Error in client handler: {e}")
#         finally:
#             conn.close()
#             active_sockets.discard(conn)
#             print(f"[-] Disconnected: {addr}")
#
#     server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#     server_socket.bind(("0.0.0.0", 25000))
#     server_socket.listen()
#
#     print(f"Socket Listening on port {25000}...")
#
#     while True:
#         conn, addr = server_socket.accept()
#         threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
#
#
#
# def get_server_ip():
#     gws = netifaces.gateways()
#     if len(gws['default']) == 0:
#         return get_my_ip()
#     return gws['default'][netifaces.AF_INET][0]
#
#
# def get_my_ip():
#     try:
#         s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#         try:
#             s.connect(("8.8.8.8", 80))
#             return s.getsockname()[0]
#         finally:
#             s.close()
#     except Exception as e:
#         try:
#             return netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
#         except (KeyError, IndexError):
#             return None
#
#
# def get_config():
#     with open("config.json", "r") as f:
#         config = json.load(f)
#     return config
#
#
# def main():
#     print("ISE NETWORK STARTING... USE CTRL-C TO EXIT")
#     config = get_config()
#     CLIENT_IP = get_my_ip()
#     SERVER_IP = get_server_ip()
#
#     print("CLIENT IP: ", CLIENT_IP)
#     print("SERVER IP: ", SERVER_IP)
#     print("-" * 10)
#
#     manager = Manager()  # Shared instance of callbacks and queues
#     mqtt_callbacks = []
#     mqtt_pub_queue = manager.Queue()
#     socket_queue = manager.Queue()
#     peer_list = manager.dict()
#
#     last_heartbeat = manager.dict()
#
#     peer_list[config['name']] = CLIENT_IP
#
#     # --- BaseManager Server Setup ---
#     class SharedManager(BaseManager): pass
#
#     SharedManager.register('get_mqtt_callbacks', callable=lambda: mqtt_callbacks, proxytype=list)
#     SharedManager.register('get_mqtt_pub_queue', callable=lambda: mqtt_pub_queue)
#     SharedManager.register('get_socket_queue', callable=lambda: socket_queue)
#     SharedManager.register('get_peer_list', callable=lambda: peer_list, proxytype=type(peer_list))
#
#     def run_manager_server():
#         m = SharedManager(address=('', 50000), authkey=b'sharedsecret')
#         server = m.get_server()
#         print("Shared manager server running at port 50000")
#         server.serve_forever()
#
#     # Start the BaseManager server in background thread
#     threading.Thread(target=run_manager_server, daemon=True).start()
#
#     # --- Start Proccesses ---
#     mqtt_process = Process(target=mqtt_listener, args=(
#         config, CLIENT_IP, SERVER_IP, mqtt_pub_queue, peer_list, last_heartbeat, mqtt_callbacks))
#     socket_process = Process(target=socket_listener, args=(config, CLIENT_IP, SERVER_IP, socket_queue))
#
#     def graceful_shutdown(signum, frame):
#         print("\n[!] Caught shutdown signal. Cleaning up...")
#
#         for s in list(active_sockets):
#             if s:
#                 try:
#                     s.close()
#                 except Exception:
#                     pass
#
#         if mqtt_process.is_alive():
#             mqtt_process.terminate()
#             mqtt_process.join()
#         if socket_process.is_alive():
#             socket_process.terminate()
#             socket_process.join()
#
#         sys.exit(0)
#
#     signal.signal(signal.SIGINT, graceful_shutdown)  # Ctrl+C
#     signal.signal(signal.SIGTERM, graceful_shutdown)  # kill
#
#     mqtt_process.start()
#     socket_process.start()
#
#     mqtt_process.join()
#     socket_process.join()
#
#     for s in list(active_sockets):
#         try:
#             s.close()
#         except Exception:
#             pass
#
#
# if __name__ == "__main__":
#     main()

import socket
import numpy as np
from multiprocessing import Process, Queue, Manager
from multiprocessing.managers import BaseManager
import paho.mqtt.client as mqtt
import time
import platform
import subprocess
import netifaces
import json
import threading
from queue import Empty
import signal
import sys

# --- Global Variables ---
active_sockets = set()
mqtt_process = None
socket_process = None
manager_server_thread = None


# --- WiFi Mesh Functions ---
def get_serial():
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


def connect_to_leader(leader_serial, prefix, interface, password):
    ssid = prefix + leader_serial
    subprocess.run(['nmcli', 'dev', 'wifi', 'connect',
                    ssid, 'ifname', interface,
                    'password', password],
                   check=True)


# --- MQTT and Socket Infrastructure ---
def mqtt_listener(config, client_ip, server_ip, publish_queue, peer_list):
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

    client = mqtt.Client()
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
    while True:
        try:
            topic, message = publish_queue.get_nowait()
            client.publish(topic, message)
        except Empty:
            continue


def socket_listener(config, client_ip, server_ip, socket_queue):
    def handle_client(conn, addr):
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
                    socket_queue.put((str(addr), data))
        except Exception as e:
            pass
        finally:
            conn.close()
            active_sockets.discard(conn)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", 25000))
    server_socket.listen()

    while True:
        conn, addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


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
def stop_network_stack():
    global mqtt_process, socket_process

    print("[Network Stack] Stopping...")
    print("[Network Stack] Clearing sockets...")
    for s in list(active_sockets):
        if s:
            try:
                s.close()
            except Exception as e:
                print(f"[Network Stack] Encountered socket error: {e}")
    active_sockets.clear()
    print("[Network Stack] Clearing sockets... Done")

    if mqtt_process and mqtt_process.is_alive():
        print("[Network Stack] Stopping MQTT Process...")
        mqtt_process.terminate()
        mqtt_process.join()
    if socket_process and socket_process.is_alive():
        print("[Network Stack] Stopping Socket Process...")
        socket_process.terminate()
        socket_process.join()


def start_network_stack(config, mqtt_pub_queue, socket_queue, peer_list):
    global mqtt_process, socket_process, manager_server_thread

    print("[Network Stack] Starting...")

    def run_manager_server():
        m = SharedManager(address=('', 50000), authkey=b'sharedsecret')
        server = m.get_server()
        server.serve_forever()

    print("[Network Stack] Starting Shared Variables...")
    manager_server_thread = threading.Thread(target=run_manager_server, daemon=True)
    manager_server_thread.start()

    print("[Network Stack] Starting MQTT Listener...")
    mqtt_process = Process(target=mqtt_listener, args=(config, get_my_ip(), get_server_ip(), mqtt_pub_queue, peer_list))
    mqtt_process.start()

    print("[Network Stack] Starting Socket Listener...")
    socket_process = Process(target=socket_listener, args=(config, get_my_ip(), get_server_ip(), socket_queue))
    socket_process.start()


def monitor_and_reelect(my_serial, config, shared_objs):
    while True:
        try:
            if platform.system().lower() == "windows":
                print(f"[Monitor] Checking connection...(Windows)")
                result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True, text=True)
                ssid_ok = any(config['LEADER_SSID_PREFIX'] in line for line in result.stdout.splitlines() if
                              "SSID" in line and "BSSID" not in line)
                if "connected" not in result.stdout.lower() or not ssid_ok:
                    raise Exception("[Monitor] Disconnected or wrong network")
            else:
                print(f"[Monitor] Checking connection...(Linux)")
                result = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'], capture_output=True,
                                        text=True, check=False)
                print(f"[Monitor] nmcli return code: {result.returncode}")
                print(f"[Monitor] nmcli stdout: {result.stdout}")
                print(f"[Monitor] nmcli stderr: {result.stderr}")
                active = [line for line in result.stdout.split('\n') if line.startswith('yes:')]
                print(f"[Monitor] Active connection...(L): {active}")
                if not active or config['LEADER_SSID_PREFIX'] not in active[0]:
                    raise Exception("[Monitor] Disconnected or wrong network")
        except Exception as e:
            print(f"[Monitor] Mesh Network Lost: {e}. Restarting...")
            try:
                stop_network_stack()
            except Exception as e:
                print(f"[Monitor] Encountered an issue trying to stop stack: {e}")
                exit()
            try:
                if config["can_configure_network"]:
                    seen = scan_wifi(config['LEADER_SSID_PREFIX'])
                    remote_serials = [extract_serial_from_ssid(ssid, config['LEADER_SSID_PREFIX']) for ssid in seen]
                    leader_serial = elect_leader(remote_serials)
                    if not leader_serial or leader_serial == my_serial:
                        print(f"[Monitor] Mesh Network Lost: {e}. Restarting...")
                        setup_ap(my_serial, config['LEADER_SSID_PREFIX'], config['LAN_INTERFACE'],
                                 config['WIFI_PASSWORD'])
                    else:
                        print(f"[Monitor] Mesh Leader Found: {leader_serial}")
                        connect_to_leader(leader_serial, config['LEADER_SSID_PREFIX'], config['LAN_INTERFACE'],
                                          config['WIFI_PASSWORD'])
                        print(f"[Monitor] Successfully connected to: {leader_serial}")

                    time.sleep(5)
                    start_network_stack(config, *shared_objs)
                else:
                    print("[Monitor] Please configure network settings... Exiting...")
                    exit()
            except Exception as ex:
                print("[Monitor] Failed trying to configure network:", ex)
        time.sleep(30)


def main():
    config = get_config()
    my_serial = get_serial()
    plat = platform.system().lower()
    print(f"[Startup] Starting ISE network, use Ctrl-C to exit at anytime")
    print(f"[Startup] Device serial: {my_serial}")
    print(f"[Startup] Device platform: {plat}")


    manager = Manager()
    mqtt_pub_queue = manager.Queue()
    socket_queue = manager.Queue()
    peer_list = manager.dict()
    peer_list[config['name']] = get_my_ip()

    SharedManager.register('get_mqtt_pub_queue', callable=lambda: mqtt_pub_queue)
    SharedManager.register('get_socket_queue', callable=lambda: socket_queue)
    SharedManager.register('get_peer_list', callable=lambda: peer_list, proxytype=type(peer_list))

    shared_objs = (mqtt_pub_queue, socket_queue, peer_list)

    print(f"[Startup] Starting Monitor...")
    threading.Thread(target=monitor_and_reelect, args=(my_serial, config, shared_objs), daemon=True).start()

    signal.signal(signal.SIGINT, lambda s, f: stop_network_stack() or sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: stop_network_stack() or sys.exit(0))

    if mqtt_process:
        mqtt_process.join()
    if socket_process:
        socket_process.join()


if __name__ == "__main__":
    main()
