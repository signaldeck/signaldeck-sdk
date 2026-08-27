from datetime import datetime


class CmdResult:
    def __init__(self, variables=None):
        self._finished = False
        self.state = []
        self.variables = dict(variables or {})

    def finish(self):
        self._finished = True

    def isFinished(self):
        return self._finished

    def appendState(self, command, **kwargs):
        data = {"command": command.name, "date": datetime.now(), **kwargs}
        self.state.append(data)
