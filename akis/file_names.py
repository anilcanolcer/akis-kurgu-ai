"""Construct sibling names within the Windows filesystem component limit."""
import hashlib
from pathlib import Path


def bounded_name(name, suffix):
    """Append a suffix, preserving ordinary names and discriminating long names with a common prefix."""
    if len((name + suffix).encode('utf-16-le')) <= 510:
        return name + suffix
    digest = hashlib.sha256(name.casefold().encode('utf-8')).hexdigest()[:16]
    ending = '-' + digest + suffix
    budget = 510 - len(ending.encode('utf-16-le'))
    prefix = name.encode('utf-16-le')[:budget].decode('utf-16-le', errors='ignore')
    return prefix + ending


def sibling_with_suffix(path, suffix):
    path = Path(path)
    return path.with_name(bounded_name(path.name, suffix))
