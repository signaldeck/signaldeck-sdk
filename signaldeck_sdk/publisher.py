"""Transport-neutral publisher contracts; implementations live in plugins."""
from typing import Any, Protocol, Callable


class Publisher(Protocol):
    async def publish(self, data: dict[str, Any]) -> None: ...
    async def shutdown(self) -> None: ...


PublisherFactory = Callable[[dict[str, Any]], Publisher]


class PublisherRegistrar(Protocol):
    def register(self, name: str, factory: PublisherFactory) -> None: ...
