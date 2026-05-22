from __future__ import annotations

import threading

from ace.services.browser_runtime import BrowserRuntimeConfig, BrowserSessionTracker


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_tracker(
    clock: FakeClock,
    *,
    idle_timeout_seconds: float = 10.0,
    stale_tab_seconds: float = 5.0,
) -> BrowserSessionTracker:
    return BrowserSessionTracker(
        BrowserRuntimeConfig(
            idle_timeout_seconds=idle_timeout_seconds,
            stale_tab_seconds=stale_tab_seconds,
        ),
        clock=clock,
    )


def test_tracks_independent_tabs_by_id():
    clock = FakeClock()
    tracker = make_tracker(clock)

    tracker.heartbeat("tab-a")
    tracker.heartbeat("tab-b")

    assert tracker.active_count() == 2

    tracker.disconnect("tab-a")

    assert tracker.active_count() == 1

    tracker.disconnect("tab-b")

    assert tracker.active_count() == 0


def test_stale_heartbeat_expires_tab():
    clock = FakeClock()
    tracker = make_tracker(clock, stale_tab_seconds=5.0)

    tracker.heartbeat("tab-a")
    clock.advance(5.0)

    assert tracker.active_count() == 1

    clock.advance(0.1)

    assert tracker.active_count() == 0

    assert tracker.shutdown_due() is False
    clock.advance(10.0)
    assert tracker.shutdown_due() is True


def test_idle_countdown_starts_only_when_no_active_tabs_remain():
    clock = FakeClock()
    tracker = make_tracker(clock, idle_timeout_seconds=10.0, stale_tab_seconds=5.0)

    tracker.heartbeat("tab-a")
    clock.advance(100.0)
    tracker.heartbeat("tab-a")
    clock.advance(9.0)

    assert tracker.shutdown_due() is False

    tracker.disconnect("tab-a")
    clock.advance(9.0)

    assert tracker.shutdown_due() is False

    clock.advance(1.0)

    assert tracker.shutdown_due() is True


def test_reconnect_cancels_idle_countdown():
    clock = FakeClock()
    tracker = make_tracker(clock, idle_timeout_seconds=10.0)

    tracker.heartbeat("tab-a")
    tracker.disconnect("tab-a")
    clock.advance(9.0)
    tracker.heartbeat("tab-b")
    clock.advance(100.0)

    assert tracker.shutdown_due() is False

    tracker.disconnect("tab-b")
    clock.advance(9.0)

    assert tracker.shutdown_due() is False

    clock.advance(1.0)

    assert tracker.shutdown_due() is True


def test_shutdown_due_only_after_idle_timeout():
    clock = FakeClock()
    tracker = make_tracker(clock, idle_timeout_seconds=10.0)

    assert tracker.shutdown_due() is False

    clock.advance(9.999)

    assert tracker.shutdown_due() is False

    clock.advance(0.001)

    assert tracker.shutdown_due() is True


def test_constructing_tracker_does_not_start_background_threads():
    before = {thread.ident for thread in threading.enumerate()}

    BrowserSessionTracker(BrowserRuntimeConfig(), clock=FakeClock())

    after = {thread.ident for thread in threading.enumerate()}
    assert after == before
