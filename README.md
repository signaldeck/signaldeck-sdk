# SignalDeck SDK

The **SignalDeck SDK** defines the public plugin API for SignalDeck.

It provides:

- Base classes for processors
- The `ApplicationContext` contract
- The `ValueProvider` registry
- Helper utilities and shared logic

The SDK contains **no web runtime implementation**.  
Concrete integrations (Flask app, rendering, storage, authentication) are implemented in `signaldeck-core`.

---

## Purpose

The SDK exists to:

- Define a stable contract for plugin development
- Separate runtime wiring from plugin logic
- Provide reusable base implementations (e.g. `DisplayProcessor`)
- Enable independent versioning of plugins and the core runtime

---

## Installation

```bash
pip install signaldeck-sdk
```

## Concurrent named script runs

`Cmd.startScript(name, **variables)` starts an independent in-memory script
instance and returns a `ScriptRun` with a unique `run_id`, its own output,
variables, start time, future and status (`running`, `stopping`, `completed`,
`failed`, `stopped`). Multiple runs of the same script can coexist.

- `cmd.getScriptRuns(name)` lists instances newest first, including active and
  the latest 20 completed runs. `include_finished=False` lists only active runs.
- `cmd.getScriptRun(run_id)` retrieves one instance.
- `cmd.stopRun(run_id)` stops only the specified active run and returns whether
  it was found running. Its status stays `stopping` until asynchronous cleanup
  finishes; only then does it become `stopped`.
- `cmd.runScript(name, **variables)` still returns a Future for compatibility.
- The legacy `cmd.current[name]` and `cmd.tasks[name]` refer to the latest
  invocation; `cmd.stop(name)` now stops all active instances of that script.

Running instances and their status are not persisted or restored on restart.
