"""In-memory state for one invocation of a named SignalDeck script."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime

from .cmdResult import CmdResult


@dataclass
class ScriptRun:
    run_id: str
    script_name: str
    started_at: datetime
    result: CmdResult
    future: Future
    stop_requested: bool = False
    finished_at: datetime | None = field(default=None)
    # Script definitions can change while runs are retained in memory. Keep
    # the secrecy classification from *this* invocation for historical UIs.
    secret_variable_names: frozenset[str] = field(default_factory=frozenset)

    @property
    def status(self) -> str:
        if not self.future.done():
            return "stopping" if self.stop_requested else "running"
        if self.stop_requested or self.future.cancelled():
            return "stopped"
        if self.future.exception() is not None:
            return "failed"
        return "completed"

