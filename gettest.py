import cv2
def on_msg(msg):
    print(f"Recieved: {msg}")



if __name__ == '__main__':
    import network

    network.subscribe("robert/command", on_msg)
    network.start_loop()

    for address, frame in network.get_next_frame():
        # do computation
        print(address, frame)
        cv2.imshow('test', frame)
        cv2.waitKey(1)

    while True:
        print("Entering forever loop")
        for address, frame in network.get_next_frame():
            # do computation
            print(address, frame)
            cv2.imshow('test', frame)
            cv2.waitKey(1)