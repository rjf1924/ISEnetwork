import socket
import numpy as np
import multiprocessing
from multiprocessing import Process, Queue, Manager
import paho.mqtt.client as mqtt
import time
import subprocess
import netifaces
import json
import threading

import network
from network import get_callback


def mqtt_listener(config, client_ip, server_ip, q):
    print(f"mqtt_listener started...")

    def on_message(client, userdata, message):
        print(f"Client: {client}")
        print(f"Userdata: {userdata}")
        print(f"Received system MQTT message: {message.payload.decode()}")
        q.put((0, message.topic, message.payload.decode()))

    def on_connect(client, userdata, flags, rc):
        print(f"MQTT Connected with result code {rc}")
        client.subscribe("#")
        client.publish("connect", f"{config['name']} {client_ip}")

    try:
        client = mqtt.Client()
        client.on_message = on_message
        client.on_connect = on_connect
        client.connect(server_ip, 1883)

        client.loop_start()

        # Handle publish queue
        while True:
            msg = q.get()
            if msg[0] == 0:  # Mqtt handler
                _, topic, message = msg
                handler = get_callback(topic)
                if handler:
                    handler(msg)
            if msg[0] == 1:
                client.publish(topic, msg)

    except Exception as e:
        print("[Error connecting MQTT Listener]")
        # print(e)


# Socket Setup
def socket_listener(config, client_ip, server_ip, q):
    print("Socket listener started...")
    def handle_client(conn, addr):
        print(f"[+] Connected: {addr}")
        while True:
            data = conn.recv(1024)
            if not data:
                break
            q.put((2, {addr}, data.decode()))
            print(f"[{addr}] {data.decode()}")
            conn.sendall(b"ACK")
        conn.close()
        print(f"[-] Disconnected: {addr}")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", 25000))
    server_socket.listen()

    print("Socket Listening on port 25000...")

    while True:
        conn, addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


def event_loop(config, client_ip, server_ip, mqtt_queue, socket_queue, peer_list):
    print("Starting main event loop...")
    while True:
        msg = mqtt_queue.get()
        if msg[0] == 0:
            if msg[1] == "connect":  # Handle new incoming connections
                name, ip = msg[2].split()  # "{config['name']} {client_ip}"
                if name not in peer_list:
                    print(f"Registered {name} under {ip}")
                    peer_list[name] = ip

        print(msg)


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
    mqtt_callbacks = manager.dict()
    mqtt_queue = manager.Queue()
    socket_queue = manager.Queue()
    peer_list = manager.dict()

    peer_list[config['name']] = CLIENT_IP
    network.init(mqtt_callbacks, mqtt_queue, socket_queue, peer_list)

    mqtt_process = Process(target=mqtt_listener, args=(config, CLIENT_IP, SERVER_IP, mqtt_queue))
    socket_process = Process(target=socket_listener, args=(config, CLIENT_IP, SERVER_IP, socket_queue))
    event_loop_process = Process(target=event_loop, args=(config, CLIENT_IP, SERVER_IP, mqtt_queue, socket_queue, peer_list))

    mqtt_process.start()
    socket_process.start()
    event_loop_process.start()

    mqtt_process.join()
    socket_process.join()
    event_loop_process.join()


if __name__ == "__main__":
    main()
