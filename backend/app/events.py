"""Fan-out of live run events to WebSocket subscribers.

Agent runs publish from worker threads; each WebSocket connection owns an
asyncio.Queue on the event loop. publish() hops threads safely via
call_soon_threadsafe.
"""
import asyncio
import threading
from collections import defaultdict


class RunEventHub:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers[run_id].discard(queue)
            if not self._subscribers[run_id]:
                del self._subscribers[run_id]

    def publish(self, run_id: str, message: dict) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        with self._lock:
            queues = list(self._subscribers.get(run_id, ()))
        for queue in queues:
            self._loop.call_soon_threadsafe(queue.put_nowait, message)
