import asyncio
import datetime
import logging
import time
import uuid

from .alias import AliasDefinition
from .alias_repository import AliasRepository
from .cmdResult import CmdResult
from .execution_context import ExecutionContext
from .script import ScriptDefinition
from .script_parser import ScriptParser
from .script_repository import ScriptRepository
from .script_statement import CommandStatement, IfStatement, SetStatement, WhileStatement


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
        alias_repository: AliasRepository | None = None,
    ):
        self.logger = logging.getLogger("cmd")
        self._loop = loop
        self.script_repository = script_repository
        self.alias_repository = alias_repository
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
        self._script_parser = ScriptParser()

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

    def registerAlias(self, alias: AliasDefinition | dict):
        if isinstance(alias, dict):
            alias = AliasDefinition.from_dict(alias)
        if not alias.name:
            raise ValueError("Alias name must not be empty")
        if not alias.value:
            raise ValueError("Alias value must not be empty")
        self.alias[alias.name] = alias.value
        return alias

    def registerAliase(self, aliase):
        for alias in aliase:
            self.registerAlias(alias)

    def listAliases(self) -> list[AliasDefinition]:
        return [
            AliasDefinition(name=name, value=self.alias[name])
            for name in sorted(self.alias)
        ]

    def getAlias(self, name: str) -> AliasDefinition | None:
        value = self.alias.get(name)
        if value is None:
            return None
        return AliasDefinition(name=name, value=value)

    def loadAliases(self):
        if self.alias_repository is None:
            return
        for alias in self.alias_repository.list():
            self.registerAlias(alias)

    def saveAlias(self, alias: AliasDefinition | dict):
        if isinstance(alias, dict):
            alias = AliasDefinition.from_dict(alias)
        if self.alias_repository is None:
            raise RuntimeError("No alias repository configured")
        self.alias_repository.save(alias)
        self.registerAlias(alias)
        return alias

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

        variables = dict(kwargs)
        for variable in script.variables:
            if variable.name not in variables and variable.default is not None:
                variables[variable.name] = variable.default

        return self.run(script.commands, name=scriptName, **variables)

    def run(self, commands, name=None, **kwargs):
        if name is None:
            name = uuid.uuid4().hex

        stop_event = asyncio.run_coroutine_threadsafe(
            self._create_event(),
            self._loop,
        ).result()
        cmd_res = CmdResult(variables=kwargs)

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
        execution = ExecutionContext(
            run_name=run_name or "<unnamed>",
            variables=dict(macros or {}),
            cmd_result=cmdRes,
            stop_event=stopEvent,
        )

        try:
            statements = self._script_parser.parse(commands)
            await self._execute_statements(statements, execution)
        except Exception as exc:
            location = ""
            if execution.current_line is not None:
                location = f" at line {execution.current_line}"
            statement = execution.current_statement or "<script>"
            error_message = (
                f"Cmd run '{execution.run_name}' failed{location} while executing "
                f"'{statement}': {type(exc).__name__}: {exc}"
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

    async def _execute_statements(
        self,
        statements: list[object],
        execution: ExecutionContext,
    ) -> None:
        for statement in statements:
            if execution.stop_event and execution.stop_event.is_set():
                self.logger.warning(
                    "Stop event received for Cmd run '%s'; stopping execution",
                    execution.run_name,
                )
                return

            await self._execute_statement(statement, execution)

    async def _execute_statement(
        self,
        statement: object,
        execution: ExecutionContext,
    ) -> None:
        if isinstance(statement, CommandStatement):
            execution.current_statement = statement.command
            execution.current_line = statement.line
            await self._run_single(
                statement.command,
                execution.cmd_result,
                execution.stop_event,
                execution.variables,
            )
            return

        if isinstance(statement, SetStatement):
            execution.current_statement = f"set {statement.name} {statement.value}"
            execution.current_line = statement.line
            execution.set(statement.name, execution.resolve(statement.value))
            return

        if isinstance(statement, IfStatement):
            execution.current_statement = f"if {statement.condition}"
            execution.current_line = statement.line
            matches = await self._evaluate_condition(statement.condition, execution)
            body = statement.then_body if matches else statement.else_body
            await self._execute_statements(body, execution)
            return

        if isinstance(statement, WhileStatement):
            while not (execution.stop_event and execution.stop_event.is_set()):
                execution.current_statement = f"while {statement.condition}"
                execution.current_line = statement.line
                if not await self._evaluate_condition(statement.condition, execution):
                    return
                await self._execute_statements(statement.body, execution)
                # Always yield once per iteration so a tight while loop cannot
                # monopolize the shared asyncio event loop.
                await asyncio.sleep(0)
            return

        raise TypeError(f"Unsupported script statement: {type(statement).__name__}")

    async def _evaluate_condition(
        self,
        condition: str,
        execution: ExecutionContext,
    ) -> bool:
        from .condition_command import ConditionCommand

        resolved = self._resolveAliase(condition)
        resolved = execution.resolve(resolved)
        parts = resolved.split(" ")
        command_name = parts[0]

        if command_name not in self.commands:
            raise ValueError(f'"{command_name}" is not a known condition command!')

        condition_command = self.commands[command_name]
        if not isinstance(condition_command, ConditionCommand):
            raise ValueError(
                f"Command '{command_name}' cannot be used as a condition"
            )

        result = await condition_command.evaluate(
            *parts[1:],
            cmdRes=execution.cmd_result,
            stopEvent=execution.stop_event,
        )
        if not isinstance(result, bool):
            raise TypeError(
                f"Condition command '{command_name}' must return bool, "
                f"got {type(result).__name__}"
            )
        return result

    def _resolveAliase(self, command):
        c = command.split(" ")[0]
        if c not in self.alias:
            return command
        resolvedAlias = self.alias[c]
        return command.replace(c, resolvedAlias, 1)

    async def _run_single(
        self,
        command,
        cmdRes,
        stopEvent: asyncio.Event,
        macros=None,
    ):
        command = self._resolveAliase(command)

        for macro, value in (macros or {}).items():
            command = command.replace(f"${macro}$", str(value))

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
