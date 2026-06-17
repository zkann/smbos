// Phase 1 needs no privileged bridge: the window loads the existing token-gated dashboard SPA, which
// already talks to the FastAPI server over its own same-origin fetch/SSE. contextIsolation + sandbox
// stay on (no nodeIntegration), so the remote page has no access to Node. Later phases (the Node
// broker / IPC) add a contextBridge API here.
