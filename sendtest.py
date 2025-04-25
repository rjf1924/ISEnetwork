import network
import time
import socket
import numpy as np
import cv2

if __name__ == "__main__":


    print(f"attempting to send...")
    #network.publish("robert/command", str(i))

    PEERS = network.get_peers()  # Get the first peer on the network
    print('PEERS: ', PEERS)
    i = 0

    connection = network.SocketConnection(PEERS['Robert'])
    while True:
        PEERS = network.get_peers()  # Get the first peer on the network
        if 'Robert' in PEERS:
            img = np.random.randint(0, 256, size=(800, 800, 3), dtype=np.uint8)
            print("Sending frame to....", PEERS['Robert'])
            connection.send(img)
            cv2.imshow('test', img)
            cv2.waitKey(1)
        else:
            break
    socket.close()

    i += 1
    #time.sleep(.5)
