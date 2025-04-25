import cv2
import numpy as np


def encode_image(img, quality=80):
    """
    Compress an image using JPEG encoding.

    Args:
        img (np.ndarray): Image array (e.g., from OpenCV).
        quality (int): JPEG quality (0–100).

    Returns:
        bytes: JPEG-encoded image as bytes.
    """
    _, encoded = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return encoded.tobytes()


def decode_image(encoded_bytes):
    """
    Decode JPEG-encoded image bytes into an OpenCV image.

    Args:
        encoded_bytes (bytes): Compressed JPEG image bytes.

    Returns:
        np.ndarray: Decoded image.
    """
    img_array = np.frombuffer(encoded_bytes, dtype=np.uint8)
    return cv2.imdecode(img_array, cv2.IMREAD_COLOR)