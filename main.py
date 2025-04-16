import socket
import numpy as np
import multiprocessing
import paho.mqtt.client as mqtt


def mqtt_listener():
    def on_message(client, userdata, message):
        print(f"Received MQTT message: {message.payload.decode()}")

    client = mqtt.Client()
    client.on_message = on_message
    client.connect("broker.hivemq.com", 1883)
    client.subscribe("your/topic")
    client.loop_forever()  # Blocking call

# Socket Setup
def socket_listener():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", 5000))
    server_socket.listen(5)

    while True:
        client_socket, addr = server_socket.accept()
        data = client_socket.recv(1024).decode()
        print(f"Received socket message: {data}")
        client_socket.close()


if __name__ == "__main__":
    mqtt_process = multiprocessing.Process(target=mqtt_listener)
    socket_process = multiprocessing.Process(target=socket_listener)

    mqtt_process.start()
    socket_process.start()

    mqtt_process.join()
    socket_process.join()
