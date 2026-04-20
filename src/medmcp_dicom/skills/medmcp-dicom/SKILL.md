---
name: medmcp-dicom
description: >
  Explore and summarise DICOM data from clinical PACS exports. Use when the
  user asks what imaging data exists in a directory, wants an overview of
  patients, studies, or series, or needs to understand the structure of an
  unorganised DICOM dump.
license: Apache-2.0
compatibility: Requires the medmcp-dicom MCP server (console script medmcp-dicom).
---

## Workflow

1. Ask for the root directory.
2. Call `explore_data(summary_only=True)`. Show `summary` as a table.
   Set `include_phi=True` only if the user explicitly asks for patient identifiers.
3. If `summary.patients > 3` → large-dataset format from summary alone. Done.
   If `summary.patients ≤ 3` → call again with `summary_only=False`, then render
   the per-patient breakdown.
4. Multiple directories: steps 2–3 per directory, separate sections, no merging.
5. If `skipped_files > 0`, mention it.

## Gotchas

- **Call on the root** — tool scans recursively; calling on subdirs gives incomplete results.
- **PHI off by default** — never set `include_phi=True` unless explicitly asked.
- **Research software** — flag clinical decision contexts before proceeding.
- **Missing tags** — empty strings and `null` mean "not recorded"; do not infer.
- **Errors** — report and stop; do not retry without asking.

## Output format

Use `—` for any missing or null value throughout.

---

### Large dataset (> 3 patients)

Statistics table only — do not enumerate patients, studies, or series.

```markdown
**DICOM Overview** — `<root_dir>`

|            |        |
|------------|--------|
| Patients   | <N>    |
| Studies    | <N>    |
| Series     | <N>    |
| Instances  | <N>    |
| Date range | <YYYY-MM-DD> – <YYYY-MM-DD> |

**Modalities**
| Modality | Series |
|----------|--------|
| <MR>     | <N>    |

**Anatomical regions**
| Body part | Series |
|-----------|--------|
| <BRAIN>   | <N>    |
| —         | <N>    |
```

- Omit the Date range row when `study_date_range` is `null`.
- `summary.modalities` and `summary.body_parts` are pre-sorted by count descending — preserve that order.
- Use `—` for the `""` key in `body_parts`.
- Omit the Anatomical regions table if `body_parts` is empty or contains only the `""` key.

---

### Small dataset (≤ 3 patients)

Same statistics table, then a per-patient breakdown.

Per study, check `series_count`:

- **> 10** → collapsed format (mandatory)
- **≤ 10** → individual format

#### Collapsed format

Collect all `study.series` entries into groups keyed by `(modality, body_part, shape)`.
Do this for **all series first**, then render **one row per group**:

```markdown
**<YYYY-MM-DD> — <Study description>**
| Modality | Body part | Series | Slices each    | Resolution                    |
|----------|-----------|--------|----------------|-------------------------------|
| <MR>     | <BRAIN>   | <N>    | <N or min–max> | <Rows>×<Cols> px, <x>×<y> mm |
| <SR>     | —         | <N>    | <N or min–max> | —                             |
```

- **Series** = total series count in the group.
- **Slices each** = instance count if constant across the group; `min–max` if it varies.
- Omit Resolution column if pixel spacing is absent for all groups.
- Omit Body part column if absent for all groups.

#### Individual format

```markdown
**<YYYY-MM-DD or — if absent> — <Study description or —>**
| Series | Modality   | Body part       | Slices | Resolution       |
|--------|------------|-----------------|--------|------------------|
| <desc> | <Modality> | <BodyPart or —> | <N>    | <Rows>×<Cols> px |
```

- Append `, <x>×<y> mm` to Resolution when `pixel_spacing_mm` is non-null.
- Omit Resolution column if absent for all series in the study.
- Omit Body part column if absent for all series in the study.
- Omit UIDs unless the user asks for them.
