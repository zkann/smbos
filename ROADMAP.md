# Roadmap

Working list, maintained as items ship. Shipped history lives in the git log.

## Next up

- Dogfood: let real use reorder this list before adding more modules.

## Later

- **Trigger-miss detection.** When a session realizes mid-task that a matching SOP existed but didn't fire, capture the phrase the user actually used and propose it as a trigger. (The protocol's implicit-feedback rule covers some of this conversationally; make it systematic.)
- **Remote MCP bridge.** The same seven MCP tools over authenticated HTTP so claude.ai web and mobile can reach the library; unlocks phone approvals. Local stdio covers Desktop today.
- **Dashboard direct editing.** Deliberately deferred: suggestions-only preserves the single propose/approve path. Revisit if dashboard suggestions see heavy real use.
- **More SmbOS modules beyond SOPs.** The "operating system" ambition: candidates include a lightweight ops journal and a contacts/commitments tracker, both file-based like SOPs.

## Principles for anything added here

Plain markdown, no lock-in. Diffs, not magic. Actions execute only where the full plugin runs. Plain words on every owner-facing surface.
