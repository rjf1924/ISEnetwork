_mqtt_callbacks = None
_mqtt_queue = None
_socket_queue = None
_peer_list = None


def init(mqtt_callbacks, mqtt_queue, socket_queue,peer_list):
    global _mqtt_callbacks, _mqtt_queue, _socket_queue, _peer_list
    _mqtt_callbacks = mqtt_callbacks
    _mqtt_queue = mqtt_queue
    _socket_queue = socket_queue
    _peer_list = peer_list


def subscribe(topic, func):
    if topic not in _mqtt_callbacks:
        _mqtt_callbacks[topic] = [func]
    else:
        _mqtt_callbacks[topic].append(func)


def publish(topic, message):
    _mqtt_queue.put((1, topic, message))


def get_callback(topic):
    if topic in _mqtt_callbacks:
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