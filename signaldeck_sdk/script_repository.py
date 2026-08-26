from __future__ import annotations

from abc import ABC, abstractmethod

from .script import ScriptDefinition


class ScriptRepository(ABC):
    @abstractmethod
    def list(self) -> list[ScriptDefinition]:
        raise NotImplementedError

    @abstractmethod
    def get(self, name: str) -> ScriptDefinition | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, script: ScriptDefinition) -> None:
        raise NotImplementedError
