import threading

from app.integrations.email.base import OutgoingEmail


class InMemorySender:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sent: list[OutgoingEmail] = []

    def send(self, message: OutgoingEmail) -> None:
        with self._lock:
            self._sent.append(message)

    @property
    def sent(self) -> list[OutgoingEmail]:
        with self._lock:
            return list(self._sent)

    def clear(self) -> None:
        with self._lock:
            self._sent.clear()
