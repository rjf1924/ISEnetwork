import pickle
import platform
from multiprocessing.managers import BaseManager
import threading
import socket
import time
import json
from config_helper import get_config


class SharedManager(BaseManager): pass


SharedManager.register('get_mqtt_pub_queue')
SharedManager.register('get_socket_queue')
SharedManager.register('get_peer_list')

m = SharedManager(address=('localhost', 50000), authkey=b'sharedsecret')
m.connect()

_mqtt_pub_queue = m.get_mqtt_pub_queue()
_socket_queue = m.get_socket_queue()
_peer_list = m.get_peer_list()

print("[Network] Network Variables Synced to Main Process...")

_local_callback_registry = {}

config = get_config()


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
    Yields the next frame in the list of frame in form ((addr,port), data)
    """
    while True:
        try:
            msg = _socket_queue.get_nowait()
            if msg is not None:
                addr_and_port, data = msg
                data_decoded = pickle.loads(data)
                addr = addr_and_port[1:-1].split(',')[0][1:-1]
                port = addr_and_port[1:-1].split(',')[1][1:]
                yield (addr, port), data_decoded
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
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, config['LAN_INTERFACE'].encode())
        s.connect((addr, 25000))
        s.sendall((size.to_bytes(4, 'big')))
        s.sendall(data)


class SocketConnection:
    """
    Establish a socket connection between two devices
    """

    def __init__(self, name, port=25000, reconnect_delay=2, reconnect_tries=-1):
        self.addr = None
        self.target_user = name
        self.port = port
        self.reconnect_delay = reconnect_delay
        self.socket = None
        self.lock = threading.Lock()
        self.interface = config['LAN_INTERFACE']
        self.reconnect_tries = reconnect_tries
        self.connect()

    def connect(self):
        tries = 0
        while tries < self.reconnect_tries or self.reconnect_tries == -1:
            try:
                if self.target_user in get_peers():
                    self.addr = resolve_ip(self.target_user)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    if platform.system() == "Linux":
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode())
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    s.connect((self.addr, self.port))

                    self.socket = s
                    print(f"[Socket Connection] Connected to {self.target_user}|{self.addr}")
                    break
                else:
                    print(f"[Socket Connection] {self.target_user} not on the network")
                    break
            except Exception as e:
                print(f"[Socket Connection] Failed to connect to {self.addr}, retrying in {self.reconnect_delay}s")
                time.sleep(self.reconnect_delay)
                tries += 1

    def send(self, frame):
        try:
            data = pickle.dumps(frame)
            size = len(data)
            payload = size.to_bytes(4, 'big') + data

            with self.lock:
                view = memoryview(payload)
                while view:
                    n = self.socket.send(view)
                    view = view[n:]

        except Exception as e:
            print(f"[Socket Connection] Error sending to {self.target_user}: {e}")
            self.close()
            self.connect()
            self.send(frame)

    def close(self):
        try:
            if self.socket:
                self.socket.close()
                self.socket = None
        except:
            pass

    def __del__(self):
        self.close()


####### PEERS ######
def get_peers():
    """
    Returns a Peer Dict with:
    {
      "User1deviceName": (IP),
      "User2deviceName": (IP),
    }
    """
    return dict(_peer_list)


def resolve_ip(name):
    """
    Gets the ip of a device on the network given name
    """
    if name in get_peers():
        return get_peers()[name]
    else:
        return None


def resolve_name(ip):
    """
    Gets the name of a device on the network given ip
    """
    for name, addr in get_peers().items():
        if addr == ip:
            return name
    return None
