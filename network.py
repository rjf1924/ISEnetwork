import pickle
from multiprocessing.managers import BaseManager
import threading
import socket


class SharedManager(BaseManager): pass



SharedManager.register('get_mqtt_pub_queue')
SharedManager.register('get_socket_queue')
SharedManager.register('get_peer_list')

m = SharedManager(address=('localhost', 50000), authkey=b'sharedsecret')
m.connect()


_mqtt_pub_queue = m.get_mqtt_pub_queue()
_socket_queue = m.get_socket_queue()
_peer_list = m.get_peer_list()

print("Network Variables Synced to Main Process...")

_local_callback_registry = {}


######## MQTT ########

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


def start_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 60001))
    threading.Thread(target=_listen_forever, args=(sock,), daemon=True).start()


def publish(topic, message):
    """
    Sends a (topic,message) object to the mqtt publish queue
    """
    _mqtt_pub_queue.put((topic, message))


######## SOCKETS ########

def get_next_frame():
    """
    Yields the next frame in the list of frame in form (addr, data)
    """
    while True:
        try:
            msg = _socket_queue.get_nowait()
            if msg is not None:
                addr, data = msg
                data_decoded = pickle.loads(data)
                yield addr, data_decoded
        except Exception:
            yield None


def send_frame(addr, frame):
    """
    Send a frame (numpy or pickelable object) over socket to an address in one-go
    """
    # TODO: handle it on a seperate thread to avoid backlog

    data = pickle.dumps(frame)
    size = len(data)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((addr, 25000))
        s.sendall((size.to_bytes(4, 'big')))
        s.sendall(data)


class SocketConnection:
    """
    Establish a socket connection between two devices
    """

    def __init__(self, addr):
        self.addr = addr
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((addr, 25000))
        self.lock = threading.Lock()

    def send(self, frame):
        try:
            data = pickle.dumps(frame)
            size = len(data)
            with self.lock:
                self.socket.sendall(size.to_bytes(4, 'big'))
                self.socket.sendall(data)
        except Exception as e:
            print(f"[PersistentSender] Error sending to {self.addr}: {e}")
            self.close()

    def close(self):
        try:
            self.socket.close()
        except:
            pass


####### PEERS ######
def get_peers():
    """
    Returns a Peer Dict with:
    {
      "User1deviceName": (IP),
      "User2deviceName": (IP),
    }
    :return:
    """
    return dict(_peer_list)
