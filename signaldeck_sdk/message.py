from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class Message:
    source: str
    content: Any
    channel: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


MessageListener = Callable[[Message], None]


class MessageBus(Protocol):
    def publish(self, message: Message) -> None:
        ...

    def subscribe(
        self,
        listener: MessageListener,
    ) -> Callable[[], None]:
        """
        Register a listener.

        Returns a callback that unregisters the listener.
        """
        ...