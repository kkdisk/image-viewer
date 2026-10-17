"""具交易性的磁碟歷史：寫入／讀回成功後才移動紀錄。"""

import os
import tempfile
import uuid
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class Snapshot:
    path: str
    state: str


class EditHistory:
    def __init__(self, limit):
        self.limit = limit
        self.undo = []
        self.redo = []
        self.directory = None

    def write(self, image, state):
        if self.directory is None:
            self.directory = tempfile.TemporaryDirectory(prefix="image_viewer_history_")
        path = os.path.join(self.directory.name, uuid.uuid4().hex + ".png")
        try:
            image.save(path, "PNG")
        except Exception:
            if os.path.exists(path):
                os.remove(path)
            raise
        return Snapshot(path, state)

    @staticmethod
    def read(snapshot):
        with Image.open(snapshot.path) as image:
            return image.copy()

    @staticmethod
    def discard(entries):
        for entry in entries:
            try:
                os.remove(entry.path)
            except OSError:
                pass
        entries.clear()

    def push(self, image, state):
        entry = self.write(image, state)
        self.discard(self.redo)
        self.undo.append(entry)
        while len(self.undo) > self.limit:
            expired = [self.undo.pop(0)]
            self.discard(expired)

    def move(self, image, state, *, redo=False, rollback=False):
        source, target = (self.redo, self.undo) if redo else (self.undo, self.redo)
        if not source:
            return None
        entry = source[-1]
        restored = self.read(entry)
        try:
            current = None if rollback else self.write(image, state)
        except Exception:
            restored.close()
            raise
        source.pop()
        if current:
            target.append(current)
        self.discard([entry])
        return restored, entry.state

    def clear(self):
        self.discard(self.undo)
        self.discard(self.redo)
        if self.directory:
            self.directory.cleanup()
            self.directory = None
