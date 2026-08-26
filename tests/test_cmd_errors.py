import asyncio
import logging
import unittest

from signaldeck_sdk import Cmd, CmdResult, Command


class FailingCommand(Command):
    def __init__(self):
        super().__init__("fail", "Always fails for testing")

    async def run(self, *args, cmdRes=None, stopEvent=None):
        raise RuntimeError("boom")


class CmdErrorHandlingTest(unittest.TestCase):
    def test_command_error_is_logged_added_to_state_and_re_raised(self):
        async def run_test():
            loop = asyncio.get_running_loop()
            cmd = Cmd(loop)
            cmd.registerCmd(FailingCommand())
            result = CmdResult()
            stop_event = asyncio.Event()

            with self.assertLogs("cmd", level=logging.ERROR) as logs:
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    await cmd._run(
                        ["fail argument"],
                        result,
                        stop_event,
                        {},
                        "test-script",
                    )

            self.assertTrue(result.isFinished())
            self.assertTrue(any("test-script" in entry for entry in logs.output))
            self.assertTrue(any("fail argument" in entry for entry in logs.output))
            self.assertEqual(result.state[-1]["command"], "cmd")
            self.assertIn("RuntimeError: boom", result.state[-1]["msg"])
            self.assertIn("fail argument", result.state[-1]["msg"])

        asyncio.run(run_test())

    def test_duplicate_command_registration_logs_warning(self):
        loop = asyncio.new_event_loop()
        try:
            cmd = Cmd(loop)
            first = Command("duplicate", "first")
            second = Command("duplicate", "second")
            cmd.registerCmd(first)

            with self.assertLogs("cmd", level=logging.WARNING) as logs:
                cmd.registerCmd(second)

            self.assertIs(cmd.commands["duplicate"], second)
            self.assertTrue(any("duplicate" in entry for entry in logs.output))
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
