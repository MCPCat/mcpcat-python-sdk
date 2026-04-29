"""Shared helpers for the e2e Streamable-HTTP test suite."""

from __future__ import annotations

import socket
import time
from typing import Optional


def find_free_port() -> int:
    """Bind to 127.0.0.1:0, capture the assigned port, release the socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> None:
    """Poll until a TCP connection succeeds. Raise TimeoutError otherwise.

    Used by uvicorn-in-thread fixtures to gate test execution on server-ready.
    """
    deadline = time.time() + timeout
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.05)
    raise TimeoutError(
        f"Port {host}:{port} not accepting connections after {timeout}s "
        f"(last error: {last_err!r})"
    )
