---
name: medmcp-template
description: >
  Placeholder skill — replace with your domain workflow guidance after scaffolding.
  Example for a neuro package: "Run brain extraction, segmentation, or registration
  on MRI scans. Use when the user asks to process, analyse, or register brain images."
license: Apache-2.0
compatibility: Requires the medmcp-template MCP server (console script medmcp-template).
---

## Overview

<!-- 2–3 sentences: what this skill does and the domain it covers. -->

This is a placeholder skill for the medmcp-template package. Replace this content
with workflow guidance for your domain tools after renaming the package.

## Workflow

<!-- Step-by-step instructions for the most common task. Be prescriptive. -->

1. Confirm the input file exists and is a supported format (NIfTI `.nii`/`.nii.gz` or DICOM).
2. Call the appropriate tool with the required parameters (see [references/TOOLS.md](references/TOOLS.md)).
3. Verify the output dict contains the expected keys before using results downstream.
4. Report the result using the output format below.

## Gotchas

- **Workspace confinement**: All output paths must be within the agreed workspace
  directory passed as `output_dir`. Never write outside it.
- **No PHI in responses**: Do not log, display, or forward patient identifiers.
  Describe files by characteristics (modality, dimensions, transfer syntax) only.
- **Structured outputs**: Tools return plain dicts — parse keys explicitly, do not
  assume field order or presence of optional keys.
- **Not for clinical use**: medmcp tools are research software. If the user describes
  a clinical decision context, flag this clearly before proceeding.

## Output format

```
Tool: <tool_name>
Input: <brief description of input — no PHI>
Result: <key values from the output dict>
Status: success | failed
```

If a tool raises an exception, report the error type and message, then stop.
Do not retry with modified inputs without asking the user first.
