from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Any, Callable

_analysis_slot = threading.BoundedSemaphore(1)
_analysis_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-analysis")
_analysis_lifecycle_lock = threading.Lock()
_analysis_accepting = True


class AnalysisBusyError(RuntimeError):
    pass


class AnalysisReservation:
    """One analysis slot which can be transferred from request to worker."""

    def __init__(self):
        self._lock = threading.Lock()
        self._submitted = False
        self._released = False

    def submit(self, function: Callable[..., Any], *args, **kwargs):
        with self._lock:
            if self._submitted or self._released:
                raise RuntimeError("analysis reservation is no longer available")
            self._submitted = True
        try:
            worker = _analysis_executor.submit(function, *args, **kwargs)
        except BaseException:
            self.release()
            raise
        worker.add_done_callback(lambda _completed: self.release())
        return worker

    def release_if_unsubmitted(self) -> None:
        with self._lock:
            should_release = not self._submitted and not self._released
        if should_release:
            self.release()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        _analysis_slot.release()


def reserve_analysis_slot() -> AnalysisReservation:
    with _analysis_lifecycle_lock:
        if not _analysis_accepting or not _analysis_slot.acquire(blocking=False):
            raise AnalysisBusyError("analysis capacity is currently unavailable")
    return AnalysisReservation()


def shutdown_analysis_executor() -> None:
    """Stop admission, then wait for the shared process executor to drain."""
    global _analysis_accepting
    with _analysis_lifecycle_lock:
        _analysis_accepting = False
    _analysis_executor.shutdown(wait=True, cancel_futures=False)


async def run_cpu_analysis(
    function: Callable[..., Any],
    *args,
    reservation: AnalysisReservation | None = None,
    **kwargs,
):
    """Run one CPU-heavy analysis outside the event loop; reject excess work.

    Capacity belongs to the submitted worker future, not to the HTTP request
    task.  Cancelling a disconnected request must not admit another analysis
    while its synchronous worker is still running.
    """
    owned_reservation = reservation or reserve_analysis_slot()
    worker = owned_reservation.submit(function, *args, **kwargs)
    completion = asyncio.wrap_future(worker)
    try:
        # Shield the concurrent future so request cancellation cannot cancel a
        # worker which has already been submitted.
        return await asyncio.shield(completion)
    except asyncio.CancelledError:
        # Keep the request coroutine alive until the synchronous worker has
        # stopped. Endpoint finally blocks may own input/output files which the
        # worker is still using, so running those cleanups early is unsafe.
        try:
            await asyncio.shield(completion)
        except BaseException:
            pass
        raise
