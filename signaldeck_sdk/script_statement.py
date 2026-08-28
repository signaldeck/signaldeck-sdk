from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandStatement:
    command: str
    line: int


@dataclass(frozen=True)
class SetStatement:
    name: str
    value: str
    line: int
    is_value_command: bool = False


@dataclass(frozen=True)
class IfStatement:
    condition: str
    then_body: list[object] = field(default_factory=list)
    else_body: list[object] = field(default_factory=list)
    line: int = 0


@dataclass(frozen=True)
class WhileStatement:
    condition: str
    body: list[object] = field(default_factory=list)
    line: int = 0
