from typing import Protocol

from app.core.enums import ScanStatus


class Scanner(Protocol):
    def scan(self, content: bytes) -> ScanStatus: ...
