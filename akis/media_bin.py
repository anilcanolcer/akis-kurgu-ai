"""Small in-memory media bin, independent of the UI."""
from pathlib import Path

class MediaBin:
    def __init__(self):
        self.paths = []
    def clear(self):
        self.paths.clear()
    def add(self, path):
        value = str(Path(path))
        if value not in self.paths:
            self.paths.append(value)
    def search(self, query):
        needle = query.strip().casefold()
        return [path for path in self.paths if needle in Path(path).name.casefold()]
