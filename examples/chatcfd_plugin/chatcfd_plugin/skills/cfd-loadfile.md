---
name: cfd-loadfile
description: Guidance on the loadFile workflow
trigger: always
---

When the user asks to "look at", "analyze", "inspect" a case:

1. If you don't know which case yet, call `listFiles` and ask the user to choose.
2. Call `loadFile(case=...)` — this returns a session_id you must reuse
   for subsequent `calculate` / `compare` / `exportData` calls.
3. Do not call `calculate` before `loadFile` for that session — the engine
   will return `session not loaded`.
