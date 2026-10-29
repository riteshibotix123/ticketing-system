import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Final

from app.integrations.storage.base import StorageError

HINT_PATTERN: Final = re.compile(r"^[a-z0-9_-]{1,32}$")
KEY_PATTERN: Final = re.compile(r"^[a-z0-9_-]{1,32}/[0-9a-f]{32}$")
CHUNK_SIZE: Final = 64 * 1024


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        if not KEY_PATTERN.fullmatch(key):
            raise StorageError("invalid storage key")
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise StorageError("storage key escapes the storage root")
        return path

    def save(self, stream: BinaryIO, key_hint: str) -> str:
        if not HINT_PATTERN.fullmatch(key_hint):
            raise StorageError("invalid storage key hint")
        key = f"{key_hint}/{uuid.uuid4().hex}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as target:
            shutil.copyfileobj(stream, target, CHUNK_SIZE)
        return key

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        if not path.is_file():
            raise StorageError("stored file is missing")
        return path.open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
