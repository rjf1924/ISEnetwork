# ISE 411 ICE Network server
# Prerequisites
None for now 
# Installation
use chmod +x install.sh
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

For sockets, you can use network.get_next_frame() which returns the address, frame of any incoming frames 

    if __name__ == '__main__':
        import network
    
        for data in network.get_next_frame():
            if data is not None:
                address, frame = data
                img = decode_image(frame)
                cv2.imshow(network.resolve_name(address[0]), img)
                cv2.waitKey(1)
    
        while True:
            print("Entering forever loop")



You can get a list of all peers on the network with

    network.get_peers()

Which returns a dictionary of available peers on the network.

known bugs:   
Sockets get stuck, run   
sudo fuser -k -n tcp 25000 
sudo fuser -k -n tcp 50000
sudo fuser -k -n tcp 60001



