import concurrent.futures
import asyncio
import threading
import time
import unittest

from signaldeck_sdk import Cmd, ScriptDefinition, ScriptVariable


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


if __name__ == "__main__":
    unittest.main()
