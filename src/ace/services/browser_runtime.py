from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock, Thread, current_thread
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class BrowserRuntimeConfig:
    enabled: bool = False
    token: str = ""
    runtime_file: Path | None = None
    idle_timeout_seconds: float = 300.0
    stale_tab_seconds: float = 45.0
    monitor_interval_seconds: float = 5.0


class BrowserSessionTracker:
    def __init__(
        self,
        config: BrowserRuntimeConfig,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config
        self._clock = clock
        self._tabs: dict[str, float] = {}
        self._idle_since: float | None = None
        self._lock = RLock()

    def heartbeat(self, tab_id: str) -> None:
        now = self._clock()
        with self._lock:
            self._tabs[tab_id] = now
            self._idle_since = None

    def disconnect(self, tab_id: str) -> None:
        with self._lock:
            self._tabs.pop(tab_id, None)
            self._refresh_idle_state()

    def active_count(self) -> int:
        with self._lock:
            self._drop_stale_tabs()
            return len(self._tabs)

    def shutdown_due(self) -> bool:
        with self._lock:
            self._refresh_idle_state()
            if self._idle_since is None:
                return False
            return self._clock() - self._idle_since >= self.config.idle_timeout_seconds

    def _refresh_idle_state(self) -> None:
        self._drop_stale_tabs()
        if self._tabs:
            self._idle_since = None
        elif self._idle_since is None:
            self._idle_since = self._clock()

    def _drop_stale_tabs(self) -> None:
        now = self._clock()
        stale_after = self.config.stale_tab_seconds
        stale_tab_ids = [
            tab_id
            for tab_id, seen_at in self._tabs.items()
            if now - seen_at > stale_after
        ]
        for tab_id in stale_tab_ids:
            self._tabs.pop(tab_id, None)


class BrowserRuntimeMonitor:
    def __init__(
        self,
        tracker: BrowserSessionTracker,
        shutdown: Callable[[], None],
    ) -> None:
        self._tracker = tracker
        self._shutdown = shutdown
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(target=self._run, name="ace-browser-runtime", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not current_thread():
            thread.join(timeout=2)
            with self._lock:
                if self._thread is thread:
                    self._thread = None

    def _run(self) -> None:
        try:
            interval = self._tracker.config.monitor_interval_seconds
            while not self._stop.wait(interval):
                if self._tracker.shutdown_due():
                    self._shutdown()
                    return
        finally:
            thread = current_thread()
            with self._lock:
                if self._thread is thread:
                    self._thread = None
