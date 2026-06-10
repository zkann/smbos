---
description: Connect the SOP library to Claude Desktop (and other MCP clients)
---

Set up the SmbOS MCP server so the user's SOPs work from Claude Desktop chat, with no terminal needed there. (Local stdio MCP reaches Desktop on this machine; Cowork usually inherits it unofficially. claude.ai web and mobile need a remote HTTP connector, which this does not provide; say so if asked.)

The server is `scripts/mcp_server.py` under the plugin root (the parent of the "Starter library:" path announced at session start). It is stdlib-only; `python3` is the only requirement.

## 1. Claude Desktop

Config file: `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS (`%APPDATA%\Claude\claude_desktop_config.json` on Windows).

1. If the file exists, read it first and MERGE; never overwrite other servers. Back it up to `claude_desktop_config.json.bak` before editing.
2. Add under `mcpServers`:

```json
"smbos": {
  "command": "python3",
  "args": ["<plugin-root>/scripts/mcp_server.py"]
}
```

(Pass the SOP directory as a second arg only if the user's library is somewhere non-standard; the server resolves `$SOP_DIR` then `~/sops` on its own.)

3. Tell the user to restart Claude Desktop, then verify by asking it "what SOPs do I have?".

## 2. What to tell the user it enables (plain words)

From Claude Desktop or their phone they can now: see and use their SOPs in any chat (Claude follows "My way" automatically), capture a new SOP by describing how they do something, fix an SOP by saying what should change, review and approve/discard automated runs that are waiting, and ask what automation has cost.

One honest caveat to state: approving from chat RECORDS the decision; the action itself executes the next time Claude Code runs on this machine (or via a scheduled run). Nothing is sent from Desktop.

## 3. Other MCP clients

For any other MCP-capable client, the wiring is the same stdio command: `python3 <plugin-root>/scripts/mcp_server.py`. For this machine's Claude Code there is no need; the plugin itself is richer here.
