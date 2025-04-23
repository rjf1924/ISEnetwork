import network
import time
import socket
import numpy as np
import cv2

if __name__ == "__main__":
    i = 0
    while True:
        print(f"attempting to send...")
        network.publish("robert/command", str(i))

        PEERS = dict(network.get_peers())  # Get the first peer on the network
        print('PEERS: ', PEERS)




        if 'Robert' in PEERS:
            img = np.random.randint(0, 256, size=(200, 200), dtype=np.uint8)
            print("Sending frame to....", PEERS['Robert'])
            network.send_frame(PEERS['Robert'],img)
            cv2.imshow('test', img)
            cv2.waitKey(0)

        i += 1
        time.sleep(5)
