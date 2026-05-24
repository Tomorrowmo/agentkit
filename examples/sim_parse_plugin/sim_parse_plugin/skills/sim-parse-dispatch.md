---
name: sim-parse-dispatch
description: How to choose between detect_format / auto_parse / parse_<solver>
trigger: always
---

Detection-first discipline:

1. User gives a path → call `detect_format(path)` first.
2. If `format` is non-null → call `auto_parse(path)`.
3. If `format` is null → call `list_parsers` and ask the user which format
   to force, or report "no parser matches" honestly.
4. Use `parse_<solver>` only on explicit user override
   ("force OpenFOAM on this", "treat as Fluent even though detect says no").
