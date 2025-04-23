import network
import time
import socket
import numpy as np

if __name__ == "__main__":
    i = 0
    while True:
        print(f"attempting to send...")
        network.publish("robert/command", str(i))

        PEERS = dict(network.get_peers())  # Get the first peer on the network
        print('PEERS: ', PEERS)


        if 'Robert' in PEERS:
            print("Sending frame to....", PEERS['Robert'])
            network.send_frame(PEERS['Robert'],('HELLO'*2000).encode())

        i += 1
        time.sleep(5)
