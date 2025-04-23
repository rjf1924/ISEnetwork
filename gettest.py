
def on_msg(msg):
    print(f"Recieved: {msg}")



if __name__ == '__main__':
    import network

    network.subscribe("robert/command", on_msg)
    network.start_loop()
    for address, frame in network.get_next_frame():
        # do computation
        print(address, frame)



    while True:
        pass