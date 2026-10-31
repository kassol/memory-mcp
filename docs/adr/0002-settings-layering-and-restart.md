# Console settings override the configuration file; startup settings apply by restart

Effective value of a setting = console value, else configuration file or environment, else code default; the console shows each setting's source and can revert to the file value. Runtime settings (providers, write and maintenance models, behaviour and tuning parameters, password, access tokens) live in SQLite and apply on save. Startup settings (port, data directory, vector backend, embedding model and dimension) are written to an override file under the data directory, because the data directory decides where SQLite is. They take effect through check then apply: the check validates the pending values and reports reasons; apply makes the process exit gracefully and the container restart policy starts it again; if the new startup settings fail, the service falls back to the last good ones and the console shows why.

## Considered Options

- Hot-reloading startup settings in process: rejected. Every storage singleton (SQLite connection, vector table, graph) is built from them at import, so hot reload means writing a process manager.

## Consequences

- In a container, port and data directory are read-only in the console: compose decides them, and changing them from inside would cut the service off or write outside the volume.
- The embedding model, its dimension and its provider are read-only in the console: stored vectors were computed with them, and a change makes every stored vector incomparable.
- Provider API keys are encrypted at rest with a key file under the data directory; backups must include that file.
