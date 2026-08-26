from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScriptVariable:
    name: str
    type: str = "str"
    default: Any | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScriptVariable":
        return cls(
            name=data["name"],
            type=data.get("type", "str"),
            default=data.get("default"),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
        }
        if self.default is not None:
            data["default"] = self.default
        return data


@dataclass(frozen=True)
class ScriptDefinition:
    name: str
    commands: list[str] = field(default_factory=list)
    variables: list[ScriptVariable] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScriptDefinition":
        return cls(
            name=data["name"],
            commands=list(data.get("commands", [])),
            variables=[ScriptVariable.from_dict(v) for v in data.get("variables", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "variables": [v.to_dict() for v in self.variables],
            "commands": list(self.commands),
        }
