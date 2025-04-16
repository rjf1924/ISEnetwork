from multiprocessing.managers import BaseManager


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


def subscribe(topic, func):
    current = _mqtt_callbacks.get(topic, [])
    current.append(func)
    _mqtt_callbacks[topic] = current  # reassign whole list


def publish(topic, message):
    _mqtt_pub_queue.put((topic, message))


def get_callbacks(topic):
    if topic in list(_mqtt_callbacks.keys()):
        return _mqtt_callbacks.get(topic)
    else:
        return None


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


def send_data(peer, data):
    pass
