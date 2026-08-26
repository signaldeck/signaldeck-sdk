import asyncio
import datetime
import logging
import time
import uuid

from .cmdResult import CmdResult
from .script import ScriptDefinition
from .script_repository import ScriptRepository


class Command:
    def __init__(self, name, help):
        self.name = name
        self.help = help

    async def run(self, *args, cmdRes=None, stopEvent=None):
        pass


class EchoCommand(Command):
    def __init__(self):
        super().__init__("echo", "Saves message to state")

    async def run(self, *messages, cmdRes=None, stopEvent=None):
        msg = " ".join(messages)
        if cmdRes is not None:
            cmdRes.appendState(self, msg=msg)
        print(msg)


class SleepCommand(Command):
    def __init__(self):
        super().__init__("sleep", "Sleep for x seconds")

    async def run(self, seconds, cmdRes=None, stopEvent=None):
        total = float(seconds)
        interval = 5
        start = time.monotonic()

        while True:
            if stopEvent and stopEvent.is_set():
                return

            remaining = total - (time.monotonic() - start)
            if remaining <= 0:
                return

            await asyncio.sleep(min(interval, remaining))


class Cmd:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        script_repository: ScriptRepository | None = None,
    ):
        self.logger = logging.getLogger("cmd")
        self._loop = loop
        self.script_repository = script_repository
        self.commands = {}
        self.current = {}
        self.alias = {}
        self.tasks = {}
        self.script: dict[str, ScriptDefinition] = {}
        self.stop_events = {}
        self._runtime_state_command = Command(
            "cmd",
            "Internal Cmd runtime state",
        )

        self.registerCmd(EchoCommand())
        self.registerCmd(SleepCommand())

    def registerCmd(self, cmdFunction):
        existing = self.commands.get(cmdFunction.name)
        if existing is not None and existing is not cmdFunction:
            self.logger.warning(
                "Replacing already registered command '%s' (%s) with %s",
                cmdFunction.name,
                type(existing).__name__,
                type(cmdFunction).__name__,
            )
        self.commands[cmdFunction.name] = cmdFunction

    def listCommands(self) -> list[Command]:
        return [self.commands[name] for name in sorted(self.commands)]

    def registerAliase(self, aliase):
        for a in aliase:
            self.alias[a["name"]] = a["value"]

    def registerScript(self, script: ScriptDefinition | dict):
        if isinstance(script, dict):
            script = ScriptDefinition.from_dict(script)
        self.script[script.name] = script
        return script

    def registerScripts(self, scripts):
        for script in scripts:
            self.registerScript(script)

    def loadScripts(self):
        if self.script_repository is None:
            return
        for script in self.script_repository.list():
            self.registerScript(script)

    def listScripts(self) -> list[ScriptDefinition]:
        return [self.script[name] for name in sorted(self.script)]

    def getScript(self, name: str) -> ScriptDefinition | None:
        return self.script.get(name)

    def saveScript(self, script: ScriptDefinition | dict):
        if isinstance(script, dict):
            script = ScriptDefinition.from_dict(script)
        if self.script_repository is None:
            raise RuntimeError("No script repository configured")
        self.script_repository.save(script)
        self.registerScript(script)
        return script

    def runScript(self, scriptName, **kwargs):
        script = self.getScript(scriptName)
        if script is None:
            raise ValueError(f"{scriptName} is not a known script")

        macros = dict(kwargs)
        for variable in script.variables:
            if variable.name not in macros and variable.default is not None:
                macros[variable.name] = variable.default

        return self.run(script.commands, name=scriptName, **macros)

    def run(self, commands, name=None, **kwargs):
        if name is None:
            name = uuid.uuid4().hex

        stop_event = asyncio.run_coroutine_threadsafe(
            self._create_event(),
            self._loop,
        ).result()
        cmd_res = CmdResult()

        self.current[name] = cmd_res
        self.stop_events[name] = stop_event

        self.logger.info(
            "Scheduling Cmd run '%s' with %s command(s)",
            name,
            len(commands),
        )

        task_future = asyncio.run_coroutine_threadsafe(
            self._run(commands, cmd_res, stop_event, kwargs, name),
            self._loop,
        )
        self.tasks[name] = task_future
        return task_future

    async def _create_event(self):
        return asyncio.Event()

    def stop(self, name):
        if name in self.stop_events:
            self.stop_events[name].set()
        if name in self.tasks:
            self.tasks[name].cancel()

    async def _run(
        self,
        commands,
        cmdRes,
        stopEvent: asyncio.Event,
        macros=None,
        run_name=None,
    ):
        current_command = None
        run_name = run_name or "<unnamed>"

        try:
            for current_command in commands:
                if stopEvent.is_set():
                    self.logger.warning(
                        "Stop event received for Cmd run '%s'; stopping execution",
                        run_name,
                    )
                    break

                await self._run_single(
                    current_command,
                    cmdRes,
                    stopEvent,
                    macros or {},
                )
        except Exception as exc:
            error_message = (
                f"Cmd run '{run_name}' failed while executing "
                f"'{current_command}': {type(exc).__name__}: {exc}"
            )

            self.logger.exception(error_message)

            if cmdRes is not None:
                cmdRes.appendState(
                    self._runtime_state_command,
                    msg=error_message,
                )

            raise
        finally:
            cmdRes.finish()

    def _resolveAliase(self, command):
        c = command.split(" ")[0]
        if c not in self.alias:
            return command
        resolvedAlias = self.alias[c]
        return command.replace(c, resolvedAlias)

    async def _run_single(
        self,
        command,
        cmdRes,
        stopEvent: asyncio.Event,
        macros=None,
    ):
        command = self._resolveAliase(command)

        for macro, value in (macros or {}).items():
            command = command.replace(f"${macro}", str(value))

        parts = command.split(" ")
        command_name = parts[0]

        if command_name not in self.commands:
            raise ValueError(f'"{command_name}" is not a known command!')

        knownCommand = self.commands[command_name]

        self.logger.info(
            "⏱ START command: %s at %s",
            command,
            datetime.datetime.now(),
        )

        await knownCommand.run(
            *parts[1:],
            cmdRes=cmdRes,
            stopEvent=stopEvent,
        )

        self.logger.info(
            "⏱ END   command: %s at %s",
            command,
            datetime.datetime.now(),
        )
