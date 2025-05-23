import network
import time
import socket
import numpy as np
import cv2
from camerautils import  encode_image

if __name__ == "__main__":

    i = 0
    print(f"attempting to send...")

    PEERS = network.get_peers()  # Get the first peer on the network
    print('PEERS: ', PEERS)


    print("Starting socket..")
    connection = network.SocketConnection(PEERS['Robert'])
    while True:
        PEERS = network.get_peers()  # Get the first peer on the network
        if 'Robert' in PEERS:
            network.publish("robert/command", str(i))

            img = np.random.randint(0, 256, size=(200, 200, 1), dtype=np.uint8)
            encoded = encode_image(img)
            print("Sending frame to....", PEERS['Robert'])
            #connection.send(encoded)
            cv2.imshow('test', img)
            cv2.waitKey(0)
            #time.sleep(0.05)  # ~20 FPS
        else:
            break
        i += 1
    print("Closed socket")
    socket.close()


    #time.sleep(.5)
