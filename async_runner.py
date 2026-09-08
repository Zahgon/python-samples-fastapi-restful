"""
Persistent asyncio event loop used to drive the async layers from Flask.

Flask is a WSGI (synchronous) framework: a request is handled on a worker
thread that has no event loop of its own, while the service, database and cache
layers of this application are asynchronous. `run_async()` bridges the two.

A single, long-lived event loop on a dedicated daemon thread is used instead of
a fresh loop per request, because both libraries below keep state bound to the
loop that created it:

- SQLAlchemy's async engine keeps pooled `aiosqlite` connections.
- `aiocache.SimpleMemoryCache` schedules TTL expiry via `loop.call_later()`, so
  cached entries only expire while that loop is still alive.

The loop is started lazily, on first use, so that it is never created before a
pre-forking server such as Gunicorn forks its workers (threads are not
inherited across `fork()`).
"""

import asyncio
import logging
import threading
from typing import Any, Coroutine, Optional, TypeVar

# https://docs.gunicorn.org/en/stable/settings.html#logger-class
logger = logging.getLogger("gunicorn.error")

T = TypeVar("T")

EVENT_LOOP_THREAD_NAME = "async-runner"

_event_loop: Optional[asyncio.AbstractEventLoop] = None
_event_loop_lock = threading.Lock()


def _start_event_loop() -> asyncio.AbstractEventLoop:
    """
    Creates a new event loop and runs it forever on a dedicated daemon thread.

    Returns:
        asyncio.AbstractEventLoop: The running event loop.
    """
    event_loop = asyncio.new_event_loop()
    thread = threading.Thread(
        target=event_loop.run_forever,
        name=EVENT_LOOP_THREAD_NAME,
        daemon=True,
    )
    thread.start()
    logger.info("Async event loop started on thread '%s'.", EVENT_LOOP_THREAD_NAME)
    return event_loop


def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Returns the process-wide event loop, starting it on first use.

    Returns:
        asyncio.AbstractEventLoop: The running event loop.
    """
    global _event_loop
    if _event_loop is None:
        with _event_loop_lock:
            if _event_loop is None:
                _event_loop = _start_event_loop()
    return _event_loop


def run_async(coroutine: Coroutine[Any, Any, T]) -> T:
    """
    Runs a coroutine on the persistent event loop and waits for its result.

    Args:
        coroutine (Coroutine): The coroutine to run.

    Returns:
        The value returned by the coroutine.

    Raises:
        BaseException: Any exception raised by the coroutine is re-raised here.
    """
    return asyncio.run_coroutine_threadsafe(coroutine, get_event_loop()).result()
