from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .cmdResult import CmdResult


@dataclass
class ExecutionContext:
    run_name: str
    variables: dict[str, Any] = field(default_factory=dict)
    cmd_result: CmdResult | None = None
    stop_event: asyncio.Event | None = None
    current_statement: str | None = None
    current_line: int | None = None

    def get(self, name: str) -> Any:
        if name not in self.variables:
            raise ValueError(f"Unknown script variable: {name}")
        return self.variables[name]

    def set(self, name: str, value: Any) -> None:
        if not name:
            raise ValueError("Script variable name must not be empty")
        self.variables[name] = value

    def resolve(self, text: str) -> str:
        resolved = str(text)
        for name, value in self.variables.items():
            resolved = resolved.replace(f"${name}$", str(value))
        return resolved
