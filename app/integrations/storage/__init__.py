from app.core.config import Settings
from app.integrations.storage.base import Storage, StorageError
from app.integrations.storage.local import LocalStorage


def build_storage(settings: Settings) -> Storage:
    return LocalStorage(settings.attachment_dir)


__all__ = ["LocalStorage", "Storage", "StorageError", "build_storage"]
