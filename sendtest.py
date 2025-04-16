import network

import time

while True:
    network.publish('test', "hello!")
    time.sleep(5)