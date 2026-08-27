from abc import ABC, abstractmethod

from .alias import AliasDefinition


class AliasRepository(ABC):
    @abstractmethod
    def list(self) -> list[AliasDefinition]:
        raise NotImplementedError

    @abstractmethod
    def save(self, alias: AliasDefinition) -> None:
        raise NotImplementedError
