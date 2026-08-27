import asyncio
import unittest

from signaldeck_sdk import Cmd, CmdResult, Command, ConditionCommand, ScriptSyntaxError


class CaptureCommand(Command):
    def __init__(self):
        super().__init__("capture", "Captures arguments for tests")
        self.calls = []

    async def run(self, *args, cmdRes=None, stopEvent=None):
        self.calls.append(" ".join(args))


class EqualsCondition(ConditionCommand):
    def __init__(self):
        super().__init__("equals", "Returns whether two values are equal")

    async def evaluate(self, left, right, cmdRes=None, stopEvent=None) -> bool:
        return left == right


class ScriptControlFlowTest(unittest.TestCase):
    def test_set_if_else_and_while_use_runtime_variables(self):
        async def run_test():
            cmd = Cmd(asyncio.get_running_loop())
            capture = CaptureCommand()
            cmd.registerCmd(capture)
            cmd.registerCmd(EqualsCondition())
            result = CmdResult(variables={"initial": "unchanged"})

            await cmd._run(
                [
                    "set count 0",
                    "if equals $count$ 0",
                    "capture then",
                    "else",
                    "capture else",
                    "end",
                    "while equals $count$ 0",
                    "capture loop",
                    "set count 1",
                    "end",
                    "capture done-$count$",
                ],
                result,
                asyncio.Event(),
                {"initial": "unchanged"},
                "control-flow-test",
            )

            self.assertEqual(capture.calls, ["then", "loop", "done-1"])
            # CmdResult keeps the immutable start snapshot; set mutates only the
            # ExecutionContext used by the running script.
            self.assertEqual(result.variables, {"initial": "unchanged"})
            self.assertTrue(result.isFinished())

        asyncio.run(run_test())

    def test_else_branch_is_executed(self):
        async def run_test():
            cmd = Cmd(asyncio.get_running_loop())
            capture = CaptureCommand()
            cmd.registerCmd(capture)
            cmd.registerCmd(EqualsCondition())
            result = CmdResult()

            await cmd._run(
                [
                    "if equals a b",
                    "capture then",
                    "else",
                    "capture else",
                    "end",
                ],
                result,
                asyncio.Event(),
                {},
                "else-test",
            )

            self.assertEqual(capture.calls, ["else"])

        asyncio.run(run_test())

    def test_normal_command_cannot_be_used_as_condition(self):
        async def run_test():
            cmd = Cmd(asyncio.get_running_loop())
            result = CmdResult()

            with self.assertRaisesRegex(
                ValueError,
                "cannot be used as a condition",
            ):
                await cmd._run(
                    ["if echo hello", "echo no", "end"],
                    result,
                    asyncio.Event(),
                    {},
                    "invalid-condition",
                )

        asyncio.run(run_test())

    def test_missing_end_is_reported_by_parser(self):
        async def run_test():
            cmd = Cmd(asyncio.get_running_loop())
            result = CmdResult()

            with self.assertRaisesRegex(ScriptSyntaxError, "Missing 'end'"):
                await cmd._run(
                    ["if equals a a", "echo hello"],
                    result,
                    asyncio.Event(),
                    {},
                    "syntax-error",
                )

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
