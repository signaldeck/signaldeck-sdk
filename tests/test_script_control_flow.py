import asyncio
import unittest

from signaldeck_sdk import (
    Cmd,
    CmdResult,
    Command,
    ConditionCommand,
    ScriptSyntaxError,
    ValueCommand,
)


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


class StaticValueCommand(ValueCommand):
    def __init__(self):
        super().__init__("value_of", "Returns its first argument")

    async def get_value(self, value, cmdRes=None, stopEvent=None):
        return value


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
            self.assertEqual(result.variables, {"initial": "unchanged"})
            self.assertTrue(result.isFinished())

        asyncio.run(run_test())

    def test_set_can_assign_value_command_result(self):
        async def run_test():
            cmd = Cmd(asyncio.get_running_loop())
            capture = CaptureCommand()
            cmd.registerCmd(capture)
            cmd.registerCmd(StaticValueCommand())
            result = CmdResult()

            await cmd._run(
                [
                    "set source 42",
                    "set answer = value_of $source$",
                    "capture $answer$",
                ],
                result,
                asyncio.Event(),
                {},
                "value-command-test",
            )

            self.assertEqual(capture.calls, ["42"])

        asyncio.run(run_test())

    def test_non_value_command_cannot_be_used_in_value_assignment(self):
        async def run_test():
            cmd = Cmd(asyncio.get_running_loop())
            result = CmdResult()

            with self.assertRaisesRegex(
                ValueError,
                "cannot be used as a value command",
            ):
                await cmd._run(
                    ["set answer = echo hello"],
                    result,
                    asyncio.Event(),
                    {},
                    "invalid-value-command",
                )

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

    def test_missing_value_command_after_equals_is_reported(self):
        parser = Cmd(asyncio.new_event_loop())._script_parser
        try:
            with self.assertRaisesRegex(ScriptSyntaxError, "Missing ValueCommand"):
                parser.parse(["set answer ="])
        finally:
            parser = None

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
