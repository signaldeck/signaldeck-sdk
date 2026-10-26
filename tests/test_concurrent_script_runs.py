import concurrent.futures
import asyncio
import threading
import time
import unittest

from signaldeck_sdk import Cmd, Command, ScriptDefinition, ScriptVariable


class SlowCleanupCommand(Command):
    def __init__(self):
        super().__init__("slow_cleanup", "Wait with observable asynchronous cleanup")
        self.started = threading.Event()
        self.cleanup_started = threading.Event()
        self.cleanup_finished = threading.Event()
        self.cleanup_release = threading.Event()

    async def run(self, mode="slow", cmdRes=None, stopEvent=None):
        if mode == "fast":
            return
        try:
            self.started.set()
            await asyncio.sleep(30)
        finally:
            self.cleanup_started.set()
            while not self.cleanup_release.is_set():
                await asyncio.sleep(0.01)
            if cmdRes is not None:
                cmdRes.appendState(self, msg="cleanup completed")
            self.cleanup_finished.set()


class ConcurrentScriptRunTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever)
        self.thread.start()
        self.cmd = Cmd(self.loop)
        self.cmd.registerScript(ScriptDefinition(
            name="monitor",
            commands=["echo monitoring_$value$", "sleep 30", "echo finished_$value$"],
            variables=[ScriptVariable(name="value", default="default")],
        ))

    def tearDown(self):
        for run in self.cmd.getScriptRuns("monitor", include_finished=False):
            self.cmd.stopRun(run.run_id)
        # concurrent.futures.Future becomes cancelled before asyncio has
        # necessarily unwound its Task; let the loop perform that cleanup.
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.05), self.loop).result(timeout=2)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3)
        self.loop.close()

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for Cmd state")

    def test_same_script_can_run_twice_with_independent_state_and_stop(self):
        first = self.cmd.startScript("monitor", value="one")
        second = self.cmd.startScript("monitor", value="two")
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual([run.run_id for run in self.cmd.getScriptRuns("monitor")],
                         [second.run_id, first.run_id])
        self.wait_until(lambda: len(first.result.state) and len(second.result.state))
        self.assertEqual(first.result.variables, {"value": "one"})
        self.assertEqual(second.result.variables, {"value": "two"})
        self.assertIn("monitoring_one", first.result.state[0]["msg"])
        self.assertIn("monitoring_two", second.result.state[0]["msg"])

        self.assertTrue(self.cmd.stopRun(first.run_id))
        self.wait_until(lambda: first.future.done())
        self.assertEqual(first.status, "stopped")
        self.assertFalse(second.future.done())
        self.assertEqual(second.status, "running")
        self.assertFalse(self.cmd.stopRun(first.run_id))
        self.assertFalse(self.cmd.stopRun("nonexistent"))

        # The older, script-name based API still exposes the latest result.
        self.assertIs(self.cmd.current["monitor"], second.result)
        self.cmd.stop("monitor")
        self.wait_until(lambda: second.future.done())
        self.assertEqual(second.status, "stopped")

    def test_legacy_run_script_returns_a_future_and_stops_all_by_name(self):
        first_future = self.cmd.runScript("monitor", value="one")
        second_future = self.cmd.runScript("monitor", value="two")
        self.assertIsInstance(first_future, concurrent.futures.Future)
        self.assertIsInstance(second_future, concurrent.futures.Future)
        self.assertEqual(len(self.cmd.getScriptRuns("monitor", include_finished=False)), 2)
        self.cmd.stop("monitor")
        self.wait_until(lambda: first_future.done() and second_future.done())
        self.assertEqual([r.status for r in self.cmd.getScriptRuns("monitor")],
                         ["stopped", "stopped"])

    def test_finished_and_failed_runs_are_distinct_and_history_is_bounded(self):
        self.cmd.registerScript(ScriptDefinition(name="fast", commands=["echo done"]))
        for _ in range(self.cmd.SCRIPT_HISTORY_LIMIT + 5):
            run = self.cmd.startScript("fast")
            run.future.result(timeout=2)
        self.wait_until(lambda: len(self.cmd.getScriptRuns("fast")) == self.cmd.SCRIPT_HISTORY_LIMIT)
        self.assertEqual(run.status, "completed")
        self.assertIs(self.cmd.getScriptRun(run.run_id), run)

        self.cmd.registerScript(ScriptDefinition(name="broken", commands=["not_a_command"]))
        broken = self.cmd.startScript("broken")
        with self.assertRaises(ValueError):
            broken.future.result(timeout=2)
        self.assertEqual(broken.status, "failed")

    def test_stopping_remains_active_until_async_finally_is_finished(self):
        cleanup = SlowCleanupCommand()
        self.cmd.registerCmd(cleanup)
        self.cmd.registerScript(ScriptDefinition(
            name="cleanup", commands=["slow_cleanup $mode$"],
            variables=[ScriptVariable(name="mode", default="slow")],
        ))
        run = self.cmd.startScript("cleanup")
        try:
            self.assertTrue(cleanup.started.wait(2))
            self.assertTrue(self.cmd.stopRun(run.run_id))
            self.assertTrue(cleanup.cleanup_started.wait(2))
            self.assertEqual(run.status, "stopping")
            self.assertFalse(run.future.done())
            self.assertFalse(run.result.isFinished())
            self.assertIn(run, self.cmd.getScriptRuns("cleanup", include_finished=False))
            self.assertFalse(self.cmd.stopRun(run.run_id))  # No second cancellation.

            # Completed siblings can be pruned during async cleanup, but the
            # still-active run must never be discarded.
            for _ in range(self.cmd.SCRIPT_HISTORY_LIMIT + 4):
                sibling = self.cmd.startScript("cleanup", mode="fast")
                sibling.future.result(timeout=2)
            self.assertIn(run, self.cmd.getScriptRuns("cleanup"))
            self.assertIs(self.cmd.getScriptRun(run.run_id), run)
        finally:
            cleanup.cleanup_release.set()
        self.assertTrue(cleanup.cleanup_finished.wait(2))
        self.wait_until(lambda: run.future.done())
        self.assertEqual(run.status, "stopped")
        self.assertTrue(run.result.isFinished())
        self.assertEqual(run.result.state[-1]["msg"], "cleanup completed")
        self.assertNotIn(run, self.cmd.getScriptRuns("cleanup", include_finished=False))

    def test_direct_run_can_be_stopped_after_script_name_is_in_history(self):
        completed = self.cmd.startScript("monitor")
        self.assertTrue(self.cmd.stopRun(completed.run_id))
        self.wait_until(lambda: completed.future.done())

        # Reusing the same string as a direct run name must not be shadowed by
        # older ScriptRun history.
        direct = self.cmd.run(["sleep 30"], name="monitor")
        self.assertIs(self.cmd.tasks["monitor"], direct)
        self.cmd.stop("monitor")
        self.wait_until(lambda: direct.done())
        self.assertTrue(direct.cancelled() or direct.exception() is None)

    def test_direct_and_script_runs_stop_even_when_script_reuses_direct_name(self):
        direct = self.cmd.run(["sleep 30"], name="monitor")
        script = self.cmd.startScript("monitor", value="two")
        self.assertIs(self.cmd.tasks["monitor"], script.future)
        self.assertFalse(direct.done())
        self.assertFalse(script.future.done())

        self.cmd.stop("monitor")
        self.wait_until(lambda: direct.done() and script.future.done())
        self.assertEqual(script.status, "stopped")


if __name__ == "__main__":
    unittest.main()
