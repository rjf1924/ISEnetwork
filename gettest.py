
def on_msg(msg):
    print(f"Recieved: {msg}")


if __name__ == '__main__':
    import network

    network.subscribe("test", on_msg)
    network.start_loop()

    while True:
        pass