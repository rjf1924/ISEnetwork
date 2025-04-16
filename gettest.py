import network



def on_message(msg):
    print(f"Recieved: {msg}")

network.subscribe("test", on_message)