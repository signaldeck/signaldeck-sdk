import uuid
from .cmdResult import CmdResult
from .script import ScriptDefinition
from .script_repository import ScriptRepository
import asyncio
import time, logging
import datetime 

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
        waited = 0
        interval = 5
        start = time.monotonic()
        while waited < total:
            if stopEvent and stopEvent.is_set():
                return
            now = time.monotonic()
            remaining = total - (now - start)
            if remaining <= 0:
                return
            nextWait = min(interval, remaining)
            await asyncio.sleep(nextWait)
            waited += nextWait

class Cmd():
    def __init__(self, loop: asyncio.AbstractEventLoop, script_repository: ScriptRepository | None = None):
        self.logger = logging.getLogger("cmd")
        self._loop = loop
        self.script_repository = script_repository
        self.commands={}
        self.current={}
        self.alias={}
        self.tasks={}
        self.script: dict[str, ScriptDefinition] = {}
        self.stop_events={}
        self.registerCmd(EchoCommand())
        self.registerCmd(SleepCommand())


    def registerCmd(self,cmdFunction):
        self.commands[cmdFunction.name]=cmdFunction
    
    def registerAliase(self,aliase):
        for a in aliase:
            self.alias[a["name"]]=a["value"]

    def registerScript(self, script: ScriptDefinition | dict):
        if isinstance(script, dict):
            script = ScriptDefinition.from_dict(script)
        self.script[script.name] = script
        return script

    def registerScripts(self,scripts):
        for script in scripts:
            self.registerScript(script)

    def loadScripts(self):
        if self.script_repository is None:
            return
        for script in self.script_repository.list():
            self.registerScript(script)

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
            raise ValueError(f'{scriptName} is not a known script')

        macros = dict(kwargs)
        for variable in script.variables:
            if variable.name not in macros and variable.default is not None:
                macros[variable.name] = variable.default

        return self.run(script.commands, name=scriptName, **macros)

    def run(self, commands, name=None, **kwargs):
        if name is None:
            name = uuid.uuid4().hex
        stop_event = asyncio.run_coroutine_threadsafe(self._create_event(), self._loop).result()
        cmd_res = CmdResult()
        self.current[name] = cmd_res
        self.stop_events[name] = stop_event
        task_future = asyncio.run_coroutine_threadsafe(
            self._run(commands, cmd_res, stop_event, kwargs),
            self._loop
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

    async def _run(self, commands, cmdRes, stopEvent: asyncio.Event, macros=None):
        try:
            for com in commands:
                if stopEvent.is_set():
                    self.logger.warning("Stop event received. Stop execution of script")
                    break
                await self._run_single(com, cmdRes, stopEvent, macros or {})
        finally:
            cmdRes.finish()

    def _resolveAliase(self,command):
        c = command.split(" ")[0]
        if c not in self.alias.keys():
            return command
        resolvedAlias = self.alias[c]
        return command.replace(c,resolvedAlias)

    async def _run_single(self, command, cmdRes, stopEvent: asyncio.Event, macros={}):
        command = self._resolveAliase(command)
        for macro in macros:
            command = command.replace(f'${macro}', str(macros[macro]))
        c = command.split(" ")
        if c[0] not in self.commands:
            raise ValueError(f'"{c[0]}" is not a known command!')
        knownCommand = self.commands[c[0]]
        self.logger.info(f'⏱ START command: {command} at {datetime.datetime.now()}')
        await knownCommand.run(*c[1:], cmdRes=cmdRes, stopEvent=stopEvent)
        self.logger.info(f'⏱ END   command: {command} at {datetime.datetime.now()}')