from multiprocessing.managers import BaseManager
import threading
import socket


class SharedManager(BaseManager): pass


SharedManager.register('get_mqtt_callbacks')
SharedManager.register('get_mqtt_pub_queue')
SharedManager.register('get_socket_queue')
SharedManager.register('get_peer_list')

m = SharedManager(address=('localhost', 50000), authkey=b'sharedsecret')
m.connect()

_mqtt_callbacks = m.get_mqtt_callbacks()
_mqtt_pub_queue = m.get_mqtt_pub_queue()
_socket_queue = m.get_socket_queue()
_peer_list = m.get_peer_list()

print("Network Variables Synced to Main Process...")

_local_callback_registry = {}


def subscribe(topic, fn):
    if topic not in _local_callback_registry:
        _local_callback_registry[topic] = []
    _local_callback_registry[topic].append(fn)


def _listen_forever(sock):
    while True:
        try:
            data = sock.recv(1024).decode()
            if "|" in data:
                topic, msg = data.split("|", 1)
                if topic in _local_callback_registry:
                    for fn in _local_callback_registry[topic]:
                        fn(msg)
        except:
            break


def get_next_frame():
    """
    Yields the next frame in the list of frame in form (addr, data)
    """
    while True:
        try:
            msg = _socket_queue.get_nowait()
            addr, data = msg
            yield (addr, data)
        except Exception:
            yield None

def send_frame(addr, frame):
    """
    Send a frame over socket to an address.
    """
    # TODO: handle it on a seperate thread to avoid backlog
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(addr, 9000)
        s.sendall(frame)


def start_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 60001))
    threading.Thread(target=_listen_forever, args=(sock,), daemon=True).start()


def publish(topic, message):
    """
    Sends a (topic,message) object to the mqtt publish queue
    """
    _mqtt_pub_queue.put((topic, message))


def get_peers():
    """
    Returns a Peer Dict with:
    {
      "User1deviceName": (IP),
      "User2deviceName": (IP),
    }
    :return:
    """
    return _peer_list


