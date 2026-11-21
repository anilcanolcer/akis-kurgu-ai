"""Publish hash-verified installer and model downloads shared by running editors."""
import hashlib
import os
import time


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def matches(path, expected):
    """Whether the file exists and its SHA-256 equals `expected` (hex, any case)."""
    try:
        return sha256_file(path).lower() == str(expected).lower()
    except OSError:
        return False


def publish(partial, target, expected):
    """A verified sibling file is ready. Windows can briefly deny a competing rename or read."""
    for attempt in range(6):
        try:
            os.replace(partial, target)
            return
        except PermissionError:
            if matches(target, expected):
                return
            if os.name != 'nt' or attempt == 5:
                raise
            time.sleep(0.04 * (attempt + 1))
