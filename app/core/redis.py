from functools import lru_cache

from redis import Redis

SOCKET_TIMEOUT_SECONDS = 0.5


@lru_cache(maxsize=4)
def get_redis(url: str) -> Redis:
    return Redis.from_url(
        url,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        health_check_interval=30,
    )
