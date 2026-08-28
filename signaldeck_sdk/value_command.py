from __future__ import annotations

from .cmd import Command


class ValueCommand(Command):
    async def get_value(self, *args, cmdRes=None, stopEvent=None):
        raise NotImplementedError

    async def run(self, *args, cmdRes=None, stopEvent=None):
        raise RuntimeError(
            f"Value command '{self.name}' can only be used with set"
        )
