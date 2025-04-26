import cv2
from camerautils import  decode_image
def on_msg(msg):
    print(f"Recieved: {msg}")



if __name__ == '__main__':
    import network

    network.subscribe("command", on_msg)
    network.start_loop()

    for data in network.get_next_frame():
        if data is not None:
            address, frame = data
            img = decode_image(frame)
            print(address)
            cv2.imshow(network.resolve_name(address[0]), img)
            cv2.waitKey(1)

    while True:
        print("Entering forever loop")