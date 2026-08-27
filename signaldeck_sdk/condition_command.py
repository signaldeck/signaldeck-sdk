from __future__ import annotations

from .cmd import Command


class ConditionCommand(Command):
    async def evaluate(self, *args, cmdRes=None, stopEvent=None) -> bool:
        raise NotImplementedError

    async def run(self, *args, cmdRes=None, stopEvent=None):
        raise RuntimeError(
            f"Condition command '{self.name}' can only be used in if/while"
        )
