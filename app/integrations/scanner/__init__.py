from app.core.config import Settings
from app.integrations.scanner.base import Scanner
from app.integrations.scanner.noop import NoopScanner


def build_scanner(_settings: Settings) -> Scanner:
    return NoopScanner()


__all__ = ["NoopScanner", "Scanner", "build_scanner"]
