import network
import time

if __name__ == "__main__":

    while True:
        print(f"attempting to send...")
        network.publish('test', "hello!")
        time.sleep(5)