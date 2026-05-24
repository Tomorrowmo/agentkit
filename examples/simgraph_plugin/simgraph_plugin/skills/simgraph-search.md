---
name: simgraph-search
description: How to use query_graph effectively
trigger: always
---

When the user asks to "find", "search", "look up" simulation files:

1. Call `query_graph` with the user's question as-is (it will be NL→Cypher
   translated server-side). Do NOT pre-process the question.
2. If 0 hits, suggest broadening one constraint (drop the owner, widen Ma range).
3. For each hit, surface `file_id` so the user can pin it for later.
4. Confidence flags: `HIGH` means measured/parsed; `MED` means LLM-extracted
   from logs; `LOW` means inferred. State the flag if not HIGH.
