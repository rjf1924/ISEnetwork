import socket
import numpy as np
from multiprocessing import Process, Queue, Manager
from multiprocessing.managers import BaseManager
import paho.mqtt.client as mqtt
import time
import subprocess
import netifaces
import json
import threading
from queue import Empty


def mqtt_listener(config, client_ip, server_ip, publish_queue: Queue, peer_list, last_heartbeat, mqtt_callbacks):
    print(f"mqtt_listener started...")
    mqtt_client_sockets = []

    def broadcast_message(topic, msg):
        dead = []
        for s in mqtt_client_sockets:
            try:
                s.sendall(f"{topic}|{msg}".encode())
            except Exception:
                dead.append(s)

        # Remove any dead sockets
        for s in dead:
            mqtt_client_sockets.remove(s)
            try:
                s.close()
            except:
                pass

    def on_message(client, userdata, message):
        # print(f"Client: {client}")
        # print(f"Userdata: {userdata}")
        msg = message.payload.decode()
        topic = message.topic
        print(f"MQTT: {topic}:{msg}")

        # Handle connect event
        if topic == "connect":
            name, ip = msg.split(":")
            if name not in peer_list:
                print(f"Registered {name} under {ip}")
                peer_list[name] = ip
                client.publish("connect", f"{config['name']}:{client_ip}")

        # Handle status events
        elif topic.startswith("status/"):
            name = topic.split("/", 1)[1]
            if msg == "offline":
                if name in peer_list:
                    print(f"{name} went offline, removing from peer_list")
                    del peer_list[name]

        elif topic.startswith("heartbeat/"):
            name = topic.split("/", 1)[1]
            last_heartbeat[name] = time.time()

        else:
            broadcast_message(topic, msg)

    def on_connect(client, userdata, flags, rc):
        print(f"MQTT Connected with result code {rc}")
        client.subscribe("#")
        client.subscribe("status/#")
        client.subscribe("heartbeat/#")
        client.publish("connect", f"{config['name']}:{client_ip}")
        client.publish(f"status/{config['name']}", "online", retain=True)

    try:
        client = mqtt.Client()
        client.on_message = on_message
        client.on_connect = on_connect
        client.will_set(f"status/{config['name']}", payload="offline", qos=1, retain=True)
        client.connect(server_ip, 1883)

        client.loop_start()

        def heartbeat_loop():
            while True:
                client.publish(f"heartbeat/{config['name']}", str(time.time()), retain=True)
                time.sleep(15)  # heartbeat interval

        def peer_watchdog():
            TIMEOUT = 60  # seconds without heartbeat = dead
            while True:
                now = time.time()
                dead = [name for name, t in last_heartbeat.items() if now - t > TIMEOUT]
                for name in dead:
                    if name in peer_list:
                        print(f"[WATCHDOG] Peer {name} silent for too long. Removing.")
                        del peer_list[name]
                        del last_heartbeat[name]
                        client.publish(f"status/{name}", "offline", retain=True)
                time.sleep(5)

        def mqtt_broadcast_server():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind(("localhost", 60001))
            server.listen()

            print("[MQTT Broadcast Server] Listening on port 60001")
            while True:
                conn, addr = server.accept()
                print(f"[MQTT subscriber connected] {addr}")
                mqtt_client_sockets.append(conn)

        threading.Thread(target=peer_watchdog, daemon=True).start()
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        threading.Thread(target=mqtt_broadcast_server, daemon=True).start()

        # Handle publish queue
        while True:
            try:
                msg = publish_queue.get_nowait()
                topic, message = msg
                client.publish(topic, message)
            except Empty:
                continue

    except Exception as e:
        print(f"[Error connecting MQTT Listener]")
        print(e)


# Socket Setup
def socket_listener(config, client_ip, server_ip, socket_queue, port=25000):
    print("Socket listener started...")

    def handle_client(conn, addr):
        print(f"[+] Connected: {addr}")
        size = int.from_bytes(conn.recv(4), 'big')
        data = b''

        while len(data) < size:
            packet = conn.recv(4096)
            if not packet:
                break
            data += packet

        socket_queue.put((str(addr), data))  # Add to queue
        print(f"[{addr}] {size}")

        conn.close()
        print(f"[-] Disconnected: {addr}")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", port))
    server_socket.listen()

    print(f"Socket Listening on port {port}...")

    while True:
        conn, addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


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


def get_config():
    with open("config.json", "r") as f:
        config = json.load(f)
    return config


def main():
    print("ISE NETWORK STARTING... USE CTRL-C TO EXIT")
    config = get_config()
    CLIENT_IP = get_my_ip()
    SERVER_IP = get_server_ip()

    print("CLIENT IP: ", CLIENT_IP)
    print("SERVER IP: ", SERVER_IP)
    print("-" * 10)

    manager = Manager()  # Shared instance of callbacks and queues
    mqtt_callbacks = []
    mqtt_pub_queue = manager.Queue()
    socket_queue = manager.Queue()
    peer_list = manager.dict()

    last_heartbeat = manager.dict()

    peer_list[config['name']] = CLIENT_IP

    # --- BaseManager Server Setup ---
    class SharedManager(BaseManager): pass

    SharedManager.register('get_mqtt_callbacks', callable=lambda: mqtt_callbacks, proxytype=list)
    SharedManager.register('get_mqtt_pub_queue', callable=lambda: mqtt_pub_queue)
    SharedManager.register('get_socket_queue', callable=lambda: socket_queue)
    SharedManager.register('get_peer_list', callable=lambda: peer_list, proxytype=type(peer_list))

    def run_manager_server():
        m = SharedManager(address=('', 50000), authkey=b'sharedsecret')
        server = m.get_server()
        print("Shared manager server running at port 50000")
        server.serve_forever()

    # Start the BaseManager server in background thread
    threading.Thread(target=run_manager_server, daemon=True).start()

    # --- Start Proccesses ---
    mqtt_process = Process(target=mqtt_listener, args=(
        config, CLIENT_IP, SERVER_IP, mqtt_pub_queue, peer_list, last_heartbeat, mqtt_callbacks))
    socket_process = Process(target=socket_listener, args=(config, CLIENT_IP, SERVER_IP, socket_queue))

    mqtt_process.start()
    socket_process.start()

    mqtt_process.join()
    socket_process.join()


if __name__ == "__main__":
    main()
