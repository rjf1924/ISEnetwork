
def on_msg(msg):
    print(f"Recieved: {msg}")



if __name__ == '__main__':
    import network

    network.subscribe("robert/command", on_msg)

    for frame, address in network.get_next_frame():
        # do computation

    network.start_loop()

    while True:
        pass