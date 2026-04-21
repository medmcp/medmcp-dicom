---
name: explore-data
description: >
  Explore and summarise DICOM data from clinical PACS exports. Use when the
  user asks what imaging data exists in a directory, wants an overview of
  patients, studies, or series, or needs to understand the structure of an
  unorganised DICOM dump.
license: Apache-2.0
compatibility: Requires the medmcp-dicom MCP server (console script medmcp-dicom).
---

## Workflow

1. Ask for the root directory if not provided.
2. Call `explore_data(summary_only=True)` (set `include_phi=True` only if the user
   explicitly requests patient identifiers). Follow the `_render` field in the result —
   it tells you whether to stop (large dataset) or call again with `summary_only=False`
   (small dataset).
3. Multiple directories: run step 2 per directory in separate sections; do not merge results.

## Gotchas

- **Call on the root** — the tool scans recursively; calling on a subdirectory gives incomplete results.
- **PHI off by default** — never set `include_phi=True` unless explicitly asked.
- **Research software** — flag clinical decision contexts before proceeding.
- **Missing tags** — empty strings and `null` mean "not recorded"; do not infer or estimate.
- **Errors** — report and stop; do not retry without asking the user.
