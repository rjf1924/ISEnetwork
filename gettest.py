import cv2
from camerautils import  decode_image
def on_msg(msg):
    print(f"Recieved: {msg}")



if __name__ == '__main__':
    import network

    network.subscribe("robert/command", on_msg)
    network.start_loop()
    for data in network.get_next_frame():
        if data is not None:
            address, frame = data
            #print(address, frame)
            img = decode_image(frame)
            cv2.imshow(str(address), img)
            cv2.waitKey(1)

    while True:
        print("Entering forever loop")