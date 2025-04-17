# ISE 411 ICE Network server
# Prerequisites
None for now 
# Installation
To install, clone this repository and run install.sh followed by run.sh
# Usage
while running your client (run.sh) import network into your own python programs to be connected to the ISE net   
example of a command publisher:   

    import network
    import time

    if __name__ == "__main__":

        while True:
            print(f"attempting to send...")
            network.publish('test', "hello!")
            time.sleep(5)

example of a command subscriber:

    def on_msg(msg):
        print(f"Recieved: {msg}")
    

    if __name__ == '__main__':
        import network
    
        network.subscribe("test", on_msg)
        network.start_loop()
    
        while True:
            pass

example of a socket publisher (camera data):  TODO   
example of a socket subscriber (camera data):  TODO   
You can get a list of all peers on the network with

    network.get_peers()



