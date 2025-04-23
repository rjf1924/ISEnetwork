import network
import time
import socket
import numpy as np

if __name__ == "__main__":
    i = 0
    while True:
        print(f"attempting to send...")
        network.publish("test", str(i))

        HOST = network.get_peers()[0]  # Get the first peer on the network

        network.send_frame(HOST,b'\x01\x02\x03\x04')
        PORT = 9000



        i += 1
        time.sleep(5)
