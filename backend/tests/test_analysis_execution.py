import asyncio
from io import BytesIO
import os
import threading
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from services.analysis_execution import AnalysisBusyError, run_cpu_analysis
from services import analysis_execution


class AnalysisExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_stops_admission_and_drains_shared_executor(self):
        original_accepting = analysis_execution._analysis_accepting
        try:
            with patch.object(analysis_execution._analysis_executor, "shutdown") as shutdown:
                await asyncio.to_thread(analysis_execution.shutdown_analysis_executor)
                shutdown.assert_called_once_with(wait=True, cancel_futures=False)
                with self.assertRaises(AnalysisBusyError):
                    analysis_execution.reserve_analysis_slot()
        finally:
            analysis_execution._analysis_accepting = original_accepting

    def test_executor_is_process_shared(self):
        first = analysis_execution._analysis_executor
        second = analysis_execution._analysis_executor
        self.assertIs(first, second)
    async def test_slow_work_does_not_block_event_loop_and_excess_is_rejected(self):
        started = threading.Event()
        release = threading.Event()

        def slow():
            started.set()
            release.wait(2)
            return "ok"

        first = asyncio.create_task(run_cpu_analysis(slow))
        await asyncio.to_thread(started.wait, 1)
        ticked = False

        async def tick():
            nonlocal ticked
            await asyncio.sleep(0)
            ticked = True

        await tick()
        self.assertTrue(ticked)
        with self.assertRaises(AnalysisBusyError):
            await run_cpu_analysis(lambda: None)
        release.set()
        self.assertEqual(await first, "ok")

    async def test_cancelled_caller_keeps_capacity_until_worker_finishes(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        active = 0
        maximum_active = 0
        active_lock = threading.Lock()

        def slow():
            nonlocal active, maximum_active
            with active_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            started.set()
            release.wait(2)
            with active_lock:
                active -= 1
            finished.set()

        first = asyncio.create_task(run_cpu_analysis(slow))
        self.assertTrue(await asyncio.to_thread(started.wait, 1))
        first.cancel()
        await asyncio.sleep(0)
        self.assertFalse(first.done())

        started_at = asyncio.get_running_loop().time()
        with self.assertRaises(AnalysisBusyError):
            await run_cpu_analysis(lambda: None)
        self.assertLess(asyncio.get_running_loop().time() - started_at, 1)
        self.assertFalse(finished.is_set())

        ticked = False

        async def docs_equivalent():
            nonlocal ticked
            await asyncio.sleep(0)
            ticked = True

        await docs_equivalent()
        self.assertTrue(ticked)
        self.assertEqual(maximum_active, 1)

        release.set()
        self.assertTrue(await asyncio.to_thread(finished.wait, 1))
        with self.assertRaises(asyncio.CancelledError):
            await first
        self.assertEqual(await run_cpu_analysis(lambda: "accepted"), "accepted")
        self.assertEqual(maximum_active, 1)

    async def test_cancelled_deck_request_returns_429_until_worker_finishes(self):
        os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
        import main

        class Upload:
            filename = "deck.png"

            def __init__(self):
                self.file = BytesIO(b"image")

        class Form(dict):
            def getlist(self, key):
                return [Upload()] if key == "images" else []

        class Request:
            async def form(self, **_kwargs):
                return Form(tournament_id="1", seed_number="1")

        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        active = 0
        maximum_active = 0
        active_lock = threading.Lock()

        def process(*_args, **_kwargs):
            nonlocal active, maximum_active
            with active_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            started.set()
            release.wait(2)
            with active_lock:
                active -= 1
            finished.set()
            return {}

        with tempfile.TemporaryDirectory() as directory, patch.object(
            main, "UPLOAD_DIR", directory
        ), patch.object(main, "process_images", side_effect=process):
            first_dependency = main.require_analysis_capacity()
            first_reservation = next(first_dependency)
            first = asyncio.create_task(
                main.analyze_deck(Request(), first_reservation)
            )
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            first.cancel()
            await asyncio.sleep(0)
            self.assertFalse(first.done())

            before = asyncio.get_running_loop().time()
            with self.assertRaises(HTTPException) as raised:
                next(main.require_analysis_capacity())
            self.assertLess(asyncio.get_running_loop().time() - before, 1)
            self.assertEqual(raised.exception.status_code, 429)
            self.assertEqual(raised.exception.headers, {"Retry-After": "5"})
            self.assertEqual(maximum_active, 1)

            docs_response = await asyncio.wait_for(asyncio.sleep(0, result="ok"), 1)
            self.assertEqual(docs_response, "ok")
            self.assertFalse(finished.is_set())

            release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 1))
            with self.assertRaises(asyncio.CancelledError):
                await first
            first_dependency.close()
            self.assertEqual(maximum_active, 1)
            self.assertEqual(await run_cpu_analysis(lambda: "third"), "third")
