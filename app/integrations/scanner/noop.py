from app.core.enums import ScanStatus


class NoopScanner:
    def scan(self, _content: bytes) -> ScanStatus:
        return ScanStatus.CLEAN
