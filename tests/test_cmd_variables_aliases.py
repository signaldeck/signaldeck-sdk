import asyncio
import unittest

from signaldeck_sdk import AliasDefinition, AliasRepository, Cmd, ScriptDefinition, ScriptVariable


class MemoryAliasRepository(AliasRepository):
    def __init__(self):
        self.items = {}

    def list(self):
        return [self.items[name] for name in sorted(self.items)]

    def save(self, alias):
        self.items[alias.name] = alias


class CmdVariablesAliasesTest(unittest.TestCase):
    def test_script_result_keeps_effective_variables_including_defaults(self):
        loop = asyncio.new_event_loop()
        try:
            cmd = Cmd(loop)
            cmd.registerScript(
                ScriptDefinition(
                    name="test",
                    commands=[],
                    variables=[
                        ScriptVariable(name="a", type="str", default="default-a"),
                        ScriptVariable(name="b", type="str", default="default-b"),
                    ],
                )
            )

            # runScript needs a running Cmd loop for scheduling. We only need to
            # inspect the result created by run(), so run the loop in a helper thread.
            import threading

            thread = threading.Thread(target=loop.run_forever)
            thread.start()
            try:
                future = cmd.runScript("test", a="explicit-a")
                future.result(timeout=2)
                result = cmd.current["test"]
                self.assertEqual(
                    result.variables,
                    {"a": "explicit-a", "b": "default-b"},
                )
            finally:
                loop.call_soon_threadsafe(loop.stop)
                thread.join(timeout=2)
        finally:
            loop.close()

    def test_alias_repository_roundtrip_updates_runtime_alias(self):
        loop = asyncio.new_event_loop()
        try:
            repository = MemoryAliasRepository()
            cmd = Cmd(loop, alias_repository=repository)

            cmd.saveAlias(AliasDefinition(name="hello", value="echo hello"))

            self.assertEqual(cmd.alias["hello"], "echo hello")
            self.assertEqual(cmd.listAliases()[0].name, "hello")
            self.assertEqual(repository.list()[0].value, "echo hello")
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
