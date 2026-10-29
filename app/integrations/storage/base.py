from typing import BinaryIO, Protocol


class StorageError(Exception):
    pass


class Storage(Protocol):
    def save(self, stream: BinaryIO, key_hint: str) -> str: ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...
